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
    QueryCoverage,
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
                source_id=self.source_id,
                status="skipped",
                execution_status="skipped",
                coverage_status="unknown",
                error="disabled",
            )
        if ctx.token:
            self.client.token = ctx.token

        resources: list[Resource] = []
        gaps: list[str] = []
        errors: list[str] = []
        seen_ids: set[int] = set()
        discovered = 0
        query_coverages: list[QueryCoverage] = []

        for qi, query in enumerate(self.queries):
            page = 1
            query_incomplete = False
            items_returned = 0
            pages_read = 0
            total_count: int | None = None
            exec_status: str = "success"
            gap_reason: str | None = None
            coverage_status = "unknown"
            hit_page_budget = False

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
                    exec_status = "failed"
                    gap_reason = "timeout_or_client_error"
                    coverage_status = "unknown"
                    break

                if resp.status_code == 304:
                    coverage_status = "complete"
                    break
                if resp.status_code != 200:
                    kind = classify_http_error(resp.status_code)
                    errors.append(f"{query} page={page}: {kind} {resp.status_code}")
                    exec_status = "failed"
                    if resp.status_code in {401}:
                        gaps.append(f"unauthorized:{query}")
                        gap_reason = "unauthorized"
                        break
                    if resp.status_code in {403, 429}:
                        gaps.append(f"rate_limited:{query}:page:{page}")
                        gap_reason = "rate_limited"
                        coverage_status = "partial"
                        break
                    gaps.append(f"http_error:{query}:page:{page}:{resp.status_code}")
                    gap_reason = f"http_{resp.status_code}"
                    coverage_status = "unknown"
                    break

                payload = json.loads(resp.text)
                pages_read += 1
                if payload.get("incomplete_results"):
                    query_incomplete = True
                    gaps.append(f"incomplete_results:{query}:page:{page}")

                items = payload.get("items") or []
                items_returned += len(items)
                total_count = payload.get("total_count")

                if not items:
                    coverage_status = "partial" if query_incomplete else "complete"
                    break

                # GitHub search hard cap ~1000
                if (
                    isinstance(total_count, int)
                    and total_count > 1000
                    and page * ctx.per_page >= 1000
                ):
                    gaps.append(f"search_cap_1000:{query}:total:{total_count}")
                    gap_reason = "search_cap"

                for item in items:
                    repo_id = item.get("id")
                    if not isinstance(repo_id, int) or repo_id in seen_ids:
                        continue
                    seen_ids.add(repo_id)
                    discovered += 1
                    resources.append(self._to_resource(item))

                if len(items) < ctx.per_page:
                    coverage_status = "partial" if query_incomplete else "complete"
                    break
                if page >= ctx.max_pages:
                    # More results may exist
                    if isinstance(total_count, int) and items_returned < min(total_count, 1000):
                        hit_page_budget = True
                        coverage_status = "partial"
                        gap_reason = gap_reason or "page_budget"
                        gaps.append(
                            f"page_budget:{query}:pages={pages_read}:returned={items_returned}:total={total_count}"
                        )
                    elif query_incomplete:
                        coverage_status = "partial"
                        gap_reason = gap_reason or "upstream_incomplete"
                    else:
                        # Exactly filled last page at budget — unknown if more
                        coverage_status = "partial"
                        gap_reason = gap_reason or "page_budget"
                        gaps.append(f"page_budget:{query}:pages={pages_read}")
                    break
                page += 1

            if query_incomplete and coverage_status == "unknown":
                coverage_status = "partial"
                gap_reason = gap_reason or "upstream_incomplete"
                gaps.append(f"coverage_gap:{query}")

            if exec_status == "success" and coverage_status == "unknown" and not hit_page_budget:
                # Finished naturally without signals of more data
                coverage_status = "complete"

            query_coverages.append(
                QueryCoverage(
                    query_id=f"gh-q{qi}",
                    query=query,
                    page_size=ctx.per_page,
                    pages_read=pages_read,
                    items_returned=items_returned,
                    total_count=total_count,
                    incomplete_results=query_incomplete,
                    execution_status=exec_status,  # type: ignore[arg-type]
                    coverage_status=coverage_status,  # type: ignore[arg-type]
                    gap_reason=gap_reason,
                )
            )

        status: str
        if errors and resources:
            status = "degraded"
        elif errors and not resources:
            status = "failed"
        else:
            status = "success"

        overall_coverage = "complete"
        if any(q.coverage_status == "partial" for q in query_coverages):
            overall_coverage = "partial"
        elif any(q.coverage_status == "unknown" for q in query_coverages):
            overall_coverage = "unknown"
        if any(q.execution_status == "failed" for q in query_coverages) and not resources:
            overall_coverage = "unknown"

        result = SourceResult(
            source_id=self.source_id,
            status=status,  # type: ignore[arg-type]
            discovered=discovered,
            candidates=len(resources),
            requests=self.client.request_count,
            coverage_gaps=gaps,
            error="; ".join(errors) if errors else None,
            time_range="search_index_current",
            execution_status="failed"
            if status == "failed"
            else ("skipped" if status == "skipped" else "success"),
            coverage_status=overall_coverage,  # type: ignore[arg-type]
            queries=query_coverages,
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
