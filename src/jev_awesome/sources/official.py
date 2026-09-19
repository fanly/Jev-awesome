from __future__ import annotations

import hashlib
import re
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
    ) -> None:
        self.pages = pages or []
        self.enabled = enabled
        self.client = client or SafeHttpClient(
            allowed_domains={"docs.typesafe.ai", "typesafe.ai", "github.com"}
        )
        self.previous_hashes = previous_hashes or {}
        self.new_hashes: dict[str, str] = {}

    def collect(self, ctx: CollectContext) -> tuple[list[Resource], SourceResult]:
        if not self.enabled:
            return [], SourceResult(source_id=self.source_id, status="skipped", error="disabled")
        resources: list[Resource] = []
        errors: list[str] = []
        gaps: list[str] = []

        for page in self.pages:
            if not page.get("enabled", True):
                continue
            url = page["url"]
            allowed = set(page.get("allowed_domains") or ["docs.typesafe.ai", "typesafe.ai"])
            try:
                validate_url_for_fetch(url, allowed_domains=allowed)
                resp = self.client.get(url, headers={"Accept": "text/markdown, text/html, */*"})
            except (UrlSafetyError, Exception) as e:  # noqa: BLE001
                errors.append(f"{url}: {e}")
                gaps.append(f"official_failed:{page.get('id', url)}")
                continue
            if resp.status_code == 304:
                continue
            if resp.status_code != 200:
                errors.append(f"{url}: {classify_http_error(resp.status_code)}")
                continue

            # Keep a bounded excerpt, not a full mirror
            text = resp.text[:50_000]
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self.new_hashes[url] = digest
            title = page.get("title") or url
            rid = stable_web_id(normalize_url(url))
            resources.append(
                Resource(
                    id=rid,
                    resource_kind=ResourceKind.OFFICIAL_DOC,
                    primary_category=None,
                    canonical_url=normalize_url(url),
                    source_identity=f"official:{page.get('id', rid)}",
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
            # Extract a few same-domain links as discovery hints only
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
        return resources, SourceResult(
            source_id=self.source_id,
            status=status,  # type: ignore[arg-type]
            discovered=len(resources),
            candidates=len(resources),
            requests=self.client.request_count,
            coverage_gaps=gaps,
            error="; ".join(errors) if errors else None,
        )
