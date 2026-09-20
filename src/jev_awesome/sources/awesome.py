"""Awesome-list radar: extract links → candidates. Never copy summaries/rankings."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from jev_awesome.dates import utc_now
from jev_awesome.models import (
    EditorialStatus,
    JevRelationship,
    OfficialStatus,
    Resource,
    ResourceKind,
    SourceResult,
    VerificationLevel,
)
from jev_awesome.normalize import content_hash, github_repo_from_url, normalize_url, stable_web_id
from jev_awesome.security import UrlSafetyError, validate_url_for_fetch
from jev_awesome.sources import CollectContext
from jev_awesome.sources.http_client import SafeHttpClient, classify_http_error

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BARE_GH_RE = re.compile(r"https?://github\.com/([\w.-]+)/([\w.-]+)", re.I)

# Patterns that look like ranking / official labels / Chinese editorial blurbs — never copy
_FORBIDDEN_SUMMARY_HINTS = re.compile(
    r"(精选|官方推荐|排名|热度|必看|强烈推荐|⭐|🥇|🥈|🥉|top\s*\d+|#\d+\s*推荐)",
    re.I,
)


def extract_candidate_urls(markdown: str) -> list[str]:
    """Extract canonical URLs only — ignore link text / surrounding commentary."""
    found: list[str] = []
    seen: set[str] = set()
    for _text, url in _MD_LINK_RE.findall(markdown or ""):
        _push_url(url, found, seen)
    for m in _BARE_GH_RE.finditer(markdown or ""):
        _push_url(m.group(0).rstrip(").,;"), found, seen)
    return found


def _push_url(url: str, found: list[str], seen: set[str]) -> None:
    try:
        n = normalize_url(url.split("#")[0].split("?")[0])
        validate_url_for_fetch(n, allowed_domains=None, resolve_dns=False)
    except (UrlSafetyError, Exception):
        return
    # Prefer repo roots over deep paths for github
    gh = github_repo_from_url(n)
    if gh:
        n = normalize_url(f"https://github.com/{gh[0]}/{gh[1]}")
    if n in seen:
        return
    seen.add(n)
    found.append(n)


def assert_no_copied_summary(resource: Resource, source_markdown: str) -> None:
    """Test helper: ensure we did not lift Chinese/ranking blurbs into summary fields."""
    for field in (resource.summary_zh, resource.summary_en, resource.developer_value):
        if not field:
            continue
        if _FORBIDDEN_SUMMARY_HINTS.search(field):
            raise AssertionError(f"awesome radar must not copy ranking/summary blurbs: {field!r}")
        # Exact multi-char Chinese sentence from source next to a link — heuristic
        if len(field) >= 8 and field in (source_markdown or ""):
            raise AssertionError("awesome radar must not copy source prose into summary")


class AwesomeRadarAdapter:
    source_id = "awesome_radar"

    def __init__(
        self,
        lists: list[dict[str, Any]] | None = None,
        *,
        client: SafeHttpClient | None = None,
        enabled: bool = True,
    ) -> None:
        self.lists = lists or []
        self.enabled = enabled
        self.client = client or SafeHttpClient(
            allowed_domains={"api.github.com", "github.com", "raw.githubusercontent.com"},
        )
        self._last_raw: dict[str, str] = {}

    def collect(self, ctx: CollectContext) -> tuple[list[Resource], SourceResult]:
        if not self.enabled:
            return [], SourceResult(
                source_id=self.source_id,
                status="skipped",
                execution_status="skipped",
                coverage_status="unknown",
                error="disabled",
            )
        if ctx.token:
            self.client.token = ctx.token

        resources: list[Resource] = []
        errors: list[str] = []
        gaps: list[str] = []
        seen_ids: set[str] = set()

        for lst in self.lists:
            if not lst.get("enabled", True):
                continue
            list_id = str(lst.get("id") or lst.get("full_name") or "list")
            full_name = lst.get("full_name")
            raw_url = lst.get("raw_url")
            try:
                text = self._fetch_markdown(full_name=full_name, raw_url=raw_url)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{list_id}: {e}")
                gaps.append(f"awesome_failed:{list_id}")
                continue
            self._last_raw[list_id] = text
            for url in extract_candidate_urls(text):
                resource = self._url_to_resource(url, list_id=list_id)
                if resource.id in seen_ids:
                    continue
                seen_ids.add(resource.id)
                # Explicitly leave editorial fields empty — never copy list prose
                resources.append(resource)

        status = "success"
        if errors and resources:
            status = "degraded"
        elif errors and not resources:
            status = "failed"
        coverage = "complete" if not gaps else ("partial" if resources else "unknown")
        return resources, SourceResult(
            source_id=self.source_id,
            status=status,  # type: ignore[arg-type]
            discovered=len(resources),
            candidates=len(resources),
            requests=self.client.request_count,
            coverage_status=coverage,  # type: ignore[arg-type]
            coverage_gaps=gaps,
            error="; ".join(errors) if errors else None,
            execution_status="failed" if status == "failed" else "success",
        )

    def _fetch_markdown(self, *, full_name: str | None, raw_url: str | None) -> str:
        if raw_url:
            resp = self.client.get(raw_url, headers={"Accept": "text/plain, text/markdown, */*"})
            if resp.status_code != 200:
                raise RuntimeError(f"{classify_http_error(resp.status_code)} {resp.status_code}")
            return resp.text[:500_000]
        if not full_name:
            raise RuntimeError("awesome list requires full_name or raw_url")
        url = f"https://api.github.com/repos/{full_name}/readme"
        resp = self.client.get(url, headers={"Accept": "application/vnd.github.raw"})
        if resp.status_code != 200:
            raise RuntimeError(f"readme {classify_http_error(resp.status_code)} {resp.status_code}")
        return resp.text[:500_000]

    def _url_to_resource(self, url: str, *, list_id: str) -> Resource:
        now = utc_now()
        gh = github_repo_from_url(url)
        if gh:
            # Without API id we use a stable web id; github_full_name for dedupe
            title = f"{gh[0]}/{gh[1]}"
            # Prefer numeric id when URL path is just owner/repo — use web id keyed by full_name
            rid = stable_web_id(normalize_url(f"https://github.com/{title}"))
            # If we somehow have numeric id in path extras we don't — keep web id
            return Resource(
                id=rid,
                resource_kind=ResourceKind.OTHER,
                canonical_url=normalize_url(f"https://github.com/{title}"),
                source_identity=f"awesome:{list_id}:{title.lower()}",
                author_or_org=gh[0],
                official_status=OfficialStatus.UNKNOWN,
                jev_relationship=JevRelationship.UNCLEAR,
                original_title=title,
                summary_en=None,
                summary_zh=None,
                first_discovered_at=now,
                editorial_status=EditorialStatus.PENDING,
                verification_level=VerificationLevel.DISCOVERED,
                content_hash=content_hash(f"awesome|{title}|{url}"),
                github_full_name=title,
                tags=["awesome_radar", f"via:{list_id}"],
            )
        host = urlparse(url).netloc
        return Resource(
            id=stable_web_id(url),
            resource_kind=ResourceKind.OTHER,
            canonical_url=normalize_url(url),
            source_identity=f"awesome:{list_id}:{normalize_url(url)}",
            author_or_org=host or None,
            official_status=OfficialStatus.UNKNOWN,
            jev_relationship=JevRelationship.UNCLEAR,
            original_title=url,
            summary_en=None,
            summary_zh=None,
            first_discovered_at=now,
            editorial_status=EditorialStatus.PENDING,
            verification_level=VerificationLevel.DISCOVERED,
            content_hash=content_hash(f"awesome|{url}"),
            tags=["awesome_radar", f"via:{list_id}"],
        )
