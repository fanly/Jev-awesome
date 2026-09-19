from __future__ import annotations

from typing import Any

import feedparser

from jev_awesome.dates import parse_flexible_date, utc_now
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


class RssAtomAdapter:
    source_id = "rss_atom"

    def __init__(
        self,
        feeds: list[dict[str, Any]] | None = None,
        *,
        client: SafeHttpClient | None = None,
        enabled: bool = True,
    ) -> None:
        self.feeds = feeds or []
        self.enabled = enabled
        self.client = client or SafeHttpClient(allow_http=False)

    def collect(self, ctx: CollectContext) -> tuple[list[Resource], SourceResult]:
        if not self.enabled:
            return [], SourceResult(source_id=self.source_id, status="skipped", error="disabled")
        resources: list[Resource] = []
        errors: list[str] = []
        gaps: list[str] = []
        seen_guids: set[str] = set()

        for feed_cfg in self.feeds:
            if not feed_cfg.get("enabled", True):
                continue
            feed_url = feed_cfg["url"]
            allowed = set(feed_cfg.get("allowed_domains") or [])
            try:
                validate_url_for_fetch(feed_url, allowed_domains=allowed or None)
                resp = self.client.get(
                    feed_url,
                    headers={
                        "Accept": "application/atom+xml, application/rss+xml, application/xml, text/xml"
                    },
                    allowed_domains=allowed or None,
                )
            except (UrlSafetyError, Exception) as e:  # noqa: BLE001
                errors.append(f"{feed_url}: {e}")
                gaps.append(f"feed_failed:{feed_cfg.get('id', feed_url)}")
                continue
            if resp.status_code != 200:
                errors.append(f"{feed_url}: {classify_http_error(resp.status_code)}")
                gaps.append(f"feed_http:{feed_cfg.get('id')}:{resp.status_code}")
                continue

            parsed = feedparser.parse(resp.text)
            for entry in parsed.entries:
                guid = (
                    getattr(entry, "id", None)
                    or getattr(entry, "guid", None)
                    or getattr(entry, "link", None)
                )
                if not guid or guid in seen_guids:
                    continue
                seen_guids.add(guid)
                link = getattr(entry, "link", None) or ""
                if not link:
                    continue
                try:
                    link_n = normalize_url(link)
                    validate_url_for_fetch(link_n, allowed_domains=None, resolve_dns=False)
                except UrlSafetyError:
                    continue
                title = getattr(entry, "title", None) or link_n
                published_raw = (
                    getattr(entry, "published", None) or getattr(entry, "updated", None) or None
                )
                published = parse_flexible_date(published_raw, source="rss")
                # Invalid/garbage dates → unknown, never today
                author = getattr(entry, "author", None)
                body = f"{title}\n{link_n}\n{guid}"
                resources.append(
                    Resource(
                        id=stable_web_id(link_n),
                        resource_kind=ResourceKind.NEWS,
                        canonical_url=link_n,
                        aliases=[str(guid)] if str(guid) != link_n else [],
                        source_identity=f"rss:{feed_cfg.get('id', 'feed')}:{guid}",
                        author_or_org=author,
                        official_status=OfficialStatus.UNKNOWN,
                        jev_relationship=JevRelationship.UNCLEAR,
                        original_title=str(title),
                        published_at=published,
                        first_discovered_at=utc_now(),
                        editorial_status=EditorialStatus.PENDING,
                        verification_level=VerificationLevel.DISCOVERED,
                        content_hash=content_hash(body),
                    )
                )

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
