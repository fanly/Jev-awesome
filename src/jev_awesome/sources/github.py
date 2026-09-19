from __future__ import annotations

import json
import os
from typing import Any

from jev_awesome.dates import parse_flexible_date, utc_now
from jev_awesome.models import (
    EditorialStatus,
    FlexibleDate,
    JevRelationship,
    Observation,
    OfficialStatus,
    Resource,
    ResourceKind,
    SourceResult,
    VerificationLevel,
)
from jev_awesome.normalize import content_hash, github_entity_id, normalize_url
from jev_awesome.sources import CollectContext
from jev_awesome.sources.http_client import SafeHttpClient, classify_http_error

DEFAULT_QUERIES = [
    "jev in:name,description,readme fork:false",
    '"typesafe.ai" in:readme fork:false',
    '"@typesafe-ai/sdk" in:readme fork:false',
    '"typesafe-sdk" in:readme fork:false',
    "topic:jev",
]


class GitHubDiscoveryAdapter:
    source_id = "github_discovery"

    def __init__(
        self,
        *,
        queries: list[str] | None = None,
        allowed_domains: set[str] | None = None,
        client: SafeHttpClient | None = None,
        enabled: bool = True,
    ) -> None:
        self.queries = queries or DEFAULT_QUERIES
        self.enabled = enabled
        self.client = client or SafeHttpClient(
            allowed_domains=allowed_domains or {"api.github.com", "github.com"},
            token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        )

    def collect(self, ctx: CollectContext) -> tuple[list[Resource], SourceResult]:
        if not self.enabled:
            return [], SourceResult(
                source_id=self.source_id, status="skipped", error="disabled"
            )
        if ctx.token:
            self.client.token = ctx.token

        resources: list[Resource] = []
        gaps: list[str] = []
        errors: list[str] = []
        seen_ids: set[int] = set()
        discovered = 0

        for query in self.queries:
            page = 1
            query_incomplete = False
            while page <= ctx.max_pages:
                self.client.wait_if_needed()
                url = (
                    "https://api.github.com/search/repositories"
                    f"?q={_quote(query)}&per_page={ctx.per_page}&page={page}"
                )
                try:
                    resp = self.client.get(
                        url,
                        headers={"Accept": "application/vnd.github+json"},
                    )
                except Exception as e:  # noqa: BLE001
                    errors.append(f"{query} page={page}: {e}")
                    gaps.append(f"query_failed:{query}:page:{page}")
                    break

                if resp.status_code == 304:
                    break
                if resp.status_code != 200:
                    kind = classify_http_error(resp.status_code)
                    errors.append(f"{query} page={page}: {kind} {resp.status_code}")
                    if resp.status_code in {401}:
                        gaps.append(f"unauthorized:{query}")
                        break
                    if resp.status_code in {403, 429}:
                        gaps.append(f"rate_limited:{query}:page:{page}")
                        break
                    gaps.append(f"http_error:{query}:page:{page}:{resp.status_code}")
                    break

                payload = json.loads(resp.text)
                if payload.get("incomplete_results"):
                    query_incomplete = True
                    gaps.append(f"incomplete_results:{query}:page:{page}")

                items = payload.get("items") or []
                if not items:
                    break

                total = payload.get("total_count", 0)
                # GitHub search hard cap ~1000
                if page * ctx.per_page >= 1000 and total > 1000:
                    gaps.append(f"search_cap_1000:{query}:total:{total}")

                for item in items:
                    repo_id = item.get("id")
                    if not isinstance(repo_id, int) or repo_id in seen_ids:
                        continue
                    seen_ids.add(repo_id)
                    discovered += 1
                    resources.append(self._to_resource(item))

                if len(items) < ctx.per_page:
                    break
                page += 1

            if query_incomplete:
                gaps.append(f"coverage_gap:{query}")

        status: str
        if errors and resources:
            status = "degraded"
        elif errors and not resources:
            status = "failed"
        else:
            status = "success"

        result = SourceResult(
            source_id=self.source_id,
            status=status,  # type: ignore[arg-type]
            discovered=discovered,
            candidates=len(resources),
            requests=self.client.request_count,
            coverage_gaps=gaps,
            error="; ".join(errors) if errors else None,
            time_range="search_index_current",
        )
        return resources, result

    def _to_resource(self, item: dict[str, Any]) -> Resource:
        now = utc_now()
        repo_id = int(item["id"])
        full_name = item.get("full_name") or ""
        html_url = item.get("html_url") or f"https://github.com/{full_name}"
        published = parse_flexible_date(item.get("created_at"), source="github.created_at")
        desc = item.get("description") or ""
        title = full_name or item.get("name") or html_url
        body = f"{title}\n{desc}\n{html_url}"
        return Resource(
            id=github_entity_id(repo_id),
            resource_kind=ResourceKind.OTHER,
            canonical_url=normalize_url(html_url),
            source_identity=f"github:{repo_id}",
            author_or_org=(full_name.split("/")[0] if "/" in full_name else None),
            official_status=OfficialStatus.UNKNOWN,
            jev_relationship=JevRelationship.UNCLEAR,
            original_title=title,
            summary_en=desc or None,
            published_at=published if published.value else FlexibleDate(),
            first_discovered_at=now,
            editorial_status=EditorialStatus.PENDING,
            verification_level=VerificationLevel.DISCOVERED,
            content_hash=content_hash(body),
            github_repo_id=repo_id,
            github_full_name=full_name,
            languages=[],
            tags=list(item.get("topics") or []),
            license_identifier=(
                (item.get("license") or {}).get("spdx_id")
                if isinstance(item.get("license"), dict)
                else None
            ),
        )

    def observation_from_item(self, item: dict[str, Any], resource_id: str) -> Observation:
        return Observation(
            resource_id=resource_id,
            observed_at=utc_now(),
            source_id=self.source_id,
            github_repo_id=item.get("id"),
            full_name=item.get("full_name"),
            stars=item.get("stargazers_count"),
            default_branch=item.get("default_branch"),
            archived=item.get("archived"),
            raw_title=item.get("full_name"),
            raw_url=item.get("html_url"),
            raw_snippet=item.get("description"),
            extras={"pushed_at": item.get("pushed_at")},
        )


def _quote(q: str) -> str:
    from urllib.parse import quote

    return quote(q, safe="")
