from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

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
from jev_awesome.normalize import content_hash, normalize_url, stable_web_id
from jev_awesome.security import UrlSafetyError, validate_url_for_fetch
from jev_awesome.sources import CollectContext
from jev_awesome.sources.http_cache import HttpBodyCache
from jev_awesome.sources.http_client import SafeHttpClient, classify_http_error

_HREF_RE = re.compile(r'href=["\'](https?://[^"\']+)["\']', re.I)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


class OfficialMonitorAdapter:
    """Discover allowed official pages and hash content — not a full-site mirror."""

    source_id = "official_monitor"

    def __init__(
        self,
        pages: list[dict[str, Any]] | None = None,
        *,
        client: SafeHttpClient | None = None,
        enabled: bool = True,
        previous_hashes: dict[str, str] | None = None,
        cache_dir: Path | None = None,
        request_budget: int = 32,
    ) -> None:
        self.pages = pages or []
        self.enabled = enabled
        self.client = client or SafeHttpClient(
            allowed_domains={"docs.typesafe.ai", "typesafe.ai", "github.com"}
        )
        self.previous_hashes = previous_hashes or {}
        self.new_hashes: dict[str, str] = {}
        self.cache = HttpBodyCache(cache_dir) if cache_dir else None
        self.request_budget = max(1, request_budget)
        self._budget_used = 0

    def _within_budget(self) -> bool:
        return self._budget_used < self.request_budget

    def _get(
        self,
        url: str,
        *,
        allowed: set[str],
        etag: str | None,
        headers: dict[str, str],
    ):
        if not self._within_budget():
            raise RuntimeError("request_budget_exhausted")
        self._budget_used += 1
        return self.client.get(url, headers=headers, etag=etag, allowed_domains=allowed)

    def collect(self, ctx: CollectContext) -> tuple[list[Resource], SourceResult]:
        if not self.enabled:
            return [], SourceResult(source_id=self.source_id, status="skipped", error="disabled")
        resources: list[Resource] = []
        errors: list[str] = []
        gaps: list[str] = []
        reused = 0

        for page in self.pages:
            if not page.get("enabled", True):
                continue
            url = page["url"]
            page_id = str(page.get("id") or stable_web_id(normalize_url(url)))
            allowed = set(page.get("allowed_domains") or ["docs.typesafe.ai", "typesafe.ai"])
            cached = self.cache.load(page_id) if self.cache else None
            etag = cached.etag if cached else None
            text: str | None = None
            try:
                validate_url_for_fetch(url, allowed_domains=allowed, resolve_dns=False)
                resp = self._get(
                    url,
                    allowed=allowed,
                    etag=etag,
                    headers={"Accept": "text/markdown, text/html, */*"},
                )
            except (UrlSafetyError, Exception) as e:  # noqa: BLE001
                errors.append(f"{url}: {e}")
                gaps.append(f"official_failed:{page_id}")
                continue

            if resp.status_code == 304:
                if cached is not None:
                    text = cached.body
                    reused += 1
                    if resp.etag and self.cache and resp.etag != cached.etag:
                        self.cache.save(page_id, url=url, etag=resp.etag, body=text)
                else:
                    # Validator/ETag known to server but local body missing/corrupt:
                    # one unconditional refetch within budget; never treat 304 as empty list.
                    gaps.append(f"etag_cache_miss:{page_id}")
                    try:
                        resp2 = self._get(
                            url,
                            allowed=allowed,
                            etag=None,
                            headers={"Accept": "text/markdown, text/html, */*"},
                        )
                    except (UrlSafetyError, Exception) as e:  # noqa: BLE001
                        errors.append(f"{url}: cache_miss_refetch:{e}")
                        gaps.append(f"official_incomplete:{page_id}")
                        continue
                    if resp2.status_code != 200:
                        errors.append(
                            f"{url}: cache_miss_refetch:{classify_http_error(resp2.status_code)}"
                        )
                        gaps.append(f"official_incomplete:{page_id}")
                        continue
                    text = resp2.text[:50_000]
                    if self.cache:
                        self.cache.save(page_id, url=url, etag=resp2.etag, body=text)
            elif resp.status_code != 200:
                errors.append(f"{url}: {classify_http_error(resp.status_code)}")
                continue
            else:
                text = resp.text[:50_000]
                if self.cache:
                    self.cache.save(page_id, url=url, etag=resp.etag, body=text)

            assert text is not None
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self.new_hashes[url] = digest
            # Unchanged body vs previous run: still emit resource identity, no fake wipe
            title = page.get("title") or url
            rid = stable_web_id(normalize_url(url))
            resources.append(
                Resource(
                    id=rid,
                    resource_kind=ResourceKind.OFFICIAL_DOC,
                    primary_category=None,
                    canonical_url=normalize_url(url),
                    source_identity=f"official:{page_id}",
                    author_or_org="TypeSafe",
                    official_status=OfficialStatus.OFFICIAL,
                    jev_relationship=JevRelationship.OFFICIAL,
                    original_title=title,
                    first_discovered_at=utc_now(),
                    editorial_status=EditorialStatus.PENDING,
                    verification_level=VerificationLevel.SOURCE_CHECKED,
                    content_hash=content_hash(text),
                    tags=["official"],
                )
            )
            links = set(_HREF_RE.findall(text)) | {m[1] for m in _MD_LINK_RE.findall(text)}
            for link in list(links)[:20]:
                try:
                    validate_url_for_fetch(link, allowed_domains=allowed, resolve_dns=False)
                except UrlSafetyError:
                    continue

        status = "success"
        if errors and resources:
            status = "degraded"
        elif errors and not resources:
            status = "failed"
        elif any(g.startswith("official_incomplete:") for g in gaps) and not resources:
            status = "failed"
        elif any(g.startswith("official_incomplete:") for g in gaps):
            status = "degraded"

        coverage = "complete"
        if any("incomplete" in g or "failed" in g or "cache_miss" in g for g in gaps):
            coverage = "partial" if resources else "unknown"

        return resources, SourceResult(
            source_id=self.source_id,
            status=status,  # type: ignore[arg-type]
            discovered=len(resources),
            candidates=len(resources),
            requests=self.client.request_count,
            coverage_status=coverage,  # type: ignore[arg-type]
            coverage_gaps=gaps + ([f"etag_reused:{reused}"] if reused else []),
            error="; ".join(errors) if errors else None,
        )
