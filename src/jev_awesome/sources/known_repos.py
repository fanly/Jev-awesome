"""Known-repo watchlist: metadata refresh + material event detection.

Stars/forks are observation-only and never treated as material events.
Material events: rename, archived, new release, major README hash change.

Curated GitHub repos from CatalogStore are auto-merged into the watchlist at runtime.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from jev_awesome.dates import parse_flexible_date, utc_now
from jev_awesome.models import (
    CatalogEvent,
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

# README hash change ratio above this → material (major)
_README_MAJOR_RATIO = 0.35


def merge_watchlist(
    configured: list[dict[str, Any]] | list[str],
    curated_resources: list[Resource],
) -> list[dict[str, str]]:
    """Merge YAML watchlist with curated github full_names (dedupe by full_name)."""
    by_name: dict[str, dict[str, str]] = {}

    def _add(full_name: str, *, note: str | None = None) -> None:
        name = full_name.strip().strip("/")
        if not name or "/" not in name:
            return
        key = name.lower()
        if key not in by_name:
            by_name[key] = {"full_name": name}
            if note:
                by_name[key]["note"] = note

    for item in configured or []:
        if isinstance(item, str):
            _add(item)
        elif isinstance(item, dict):
            fn = str(item.get("full_name") or item.get("repo") or "")
            _add(fn, note=item.get("note"))

    for r in curated_resources:
        if r.editorial_status != EditorialStatus.CURATED:
            continue
        if r.github_full_name:
            _add(r.github_full_name, note="from_curated_catalog")
        else:
            from jev_awesome.normalize import github_repo_from_url

            gh = github_repo_from_url(r.canonical_url)
            if gh:
                _add(f"{gh[0]}/{gh[1]}", note="from_curated_catalog")

    return sorted(by_name.values(), key=lambda x: x["full_name"].lower())


def _readme_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _hash_distance(a: str | None, b: str | None) -> float:
    """Crude distance: 0 identical, 1 fully different (hex nibble mismatch ratio)."""
    if not a or not b:
        return 1.0 if a != b else 0.0
    if a == b:
        return 0.0
    n = min(len(a), len(b))
    if n == 0:
        return 1.0
    mism = sum(1 for i in range(n) if a[i] != b[i])
    mism += abs(len(a) - len(b))
    return min(1.0, mism / max(len(a), len(b), 1))


class KnownRepoWatchAdapter:
    source_id = "known_repo_watch"

    def __init__(
        self,
        repos: list[dict[str, Any]] | list[str] | None = None,
        *,
        curated_resources: list[Resource] | None = None,
        previous_snapshots: dict[str, dict[str, Any]] | None = None,
        client: SafeHttpClient | None = None,
        enabled: bool = True,
    ) -> None:
        self.watchlist = merge_watchlist(repos or [], curated_resources or [])
        self.previous_snapshots = previous_snapshots or {}
        self.new_snapshots: dict[str, dict[str, Any]] = {}
        self.material_events: list[CatalogEvent] = []
        self.enabled = enabled
        self.client = client or SafeHttpClient(
            allowed_domains={"api.github.com", "github.com"},
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
        errors: list[str] = []
        gaps: list[str] = []
        discovered = 0

        for entry in self.watchlist:
            full_name = entry["full_name"]
            try:
                meta = self._fetch_repo(full_name)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{full_name}: {e}")
                gaps.append(f"repo_failed:{full_name}")
                continue

            if meta is None:
                gaps.append(f"repo_missing:{full_name}")
                continue

            readme_digest = None
            try:
                readme_digest = self._fetch_readme_hash(full_name)
            except Exception as e:  # noqa: BLE001
                gaps.append(f"readme_failed:{full_name}:{e}")

            release_tag = None
            try:
                release_tag = self._fetch_latest_release(full_name)
            except Exception as e:  # noqa: BLE001
                gaps.append(f"release_failed:{full_name}:{e}")

            snapshot = {
                "id": meta.get("id"),
                "full_name": meta.get("full_name") or full_name,
                "archived": bool(meta.get("archived")),
                "default_branch": meta.get("default_branch"),
                "pushed_at": meta.get("pushed_at"),
                "latest_release": release_tag,
                "topics": list(meta.get("topics") or []),
                "license": ((meta.get("license") or {}) or {}).get("spdx_id")
                if isinstance(meta.get("license"), dict)
                else None,
                "homepage": meta.get("homepage"),
                "readme_hash": readme_digest,
                # observation-only
                "stars": meta.get("stargazers_count"),
                "forks": meta.get("forks_count"),
            }
            key = snapshot["full_name"].lower()
            self.new_snapshots[key] = snapshot
            prev = self.previous_snapshots.get(key) or self.previous_snapshots.get(
                full_name.lower()
            )

            resource = self._to_resource(meta)
            resources.append(resource)
            discovered += 1

            # Observation always includes stars/forks (non-material)
            _ = Observation(
                resource_id=resource.id,
                observed_at=utc_now(),
                source_id=self.source_id,
                github_repo_id=meta.get("id"),
                full_name=snapshot["full_name"],
                stars=snapshot["stars"],
                default_branch=snapshot["default_branch"],
                archived=snapshot["archived"],
                latest_release=release_tag,
                content_hash=readme_digest,
                raw_title=snapshot["full_name"],
                raw_url=meta.get("html_url"),
                raw_snippet=meta.get("description"),
                extras={
                    "pushed_at": snapshot["pushed_at"],
                    "forks": snapshot["forks"],
                    "topics": snapshot["topics"],
                    "homepage": snapshot["homepage"],
                    "license": snapshot["license"],
                },
            )

            if prev:
                self._detect_material(resource.id, prev, snapshot)

        status = "success"
        if errors and resources:
            status = "degraded"
        elif errors and not resources:
            status = "failed"

        coverage = "complete"
        if gaps and resources:
            coverage = "partial"
        elif gaps and not resources:
            coverage = "unknown"

        return resources, SourceResult(
            source_id=self.source_id,
            status=status,  # type: ignore[arg-type]
            discovered=discovered,
            candidates=len(resources),
            requests=self.client.request_count,
            coverage_status=coverage,  # type: ignore[arg-type]
            coverage_gaps=gaps,
            error="; ".join(errors) if errors else None,
            execution_status="failed" if status == "failed" else "success",
        )

    def _detect_material(self, resource_id: str, prev: dict, snap: dict) -> None:
        now = utc_now()
        if (
            prev.get("full_name")
            and snap.get("full_name")
            and prev["full_name"] != snap["full_name"]
        ):
            self.material_events.append(
                CatalogEvent(
                    id=f"evt-rename-{content_hash(resource_id + snap['full_name'])[:12]}",
                    event_type="doc_change",
                    resource_id=resource_id,
                    occurred_at=now,
                    summary=f"repo renamed {prev['full_name']} → {snap['full_name']}",
                    material=True,
                )
            )
        if (not prev.get("archived")) and snap.get("archived"):
            self.material_events.append(
                CatalogEvent(
                    id=f"evt-arch-{content_hash(resource_id)[:12]}",
                    event_type="doc_change",
                    resource_id=resource_id,
                    occurred_at=now,
                    summary=f"{snap['full_name']} archived",
                    material=True,
                )
            )
        prev_rel = prev.get("latest_release")
        new_rel = snap.get("latest_release")
        if new_rel and new_rel != prev_rel:
            self.material_events.append(
                CatalogEvent(
                    id=f"evt-rel-{content_hash(resource_id + str(new_rel))[:12]}",
                    event_type="new_version",
                    resource_id=resource_id,
                    occurred_at=now,
                    summary=f"new release {new_rel} on {snap['full_name']}",
                    material=True,
                )
            )
        dist = _hash_distance(prev.get("readme_hash"), snap.get("readme_hash"))
        if prev.get("readme_hash") and snap.get("readme_hash") and dist >= _README_MAJOR_RATIO:
            self.material_events.append(
                CatalogEvent(
                    id=f"evt-readme-{content_hash(resource_id + str(snap['readme_hash']))[:12]}",
                    event_type="doc_change",
                    resource_id=resource_id,
                    occurred_at=now,
                    summary=f"major README change on {snap['full_name']} (distance={dist:.2f})",
                    material=True,
                )
            )
        # stars/forks intentionally ignored for material

    def _fetch_repo(self, full_name: str) -> dict[str, Any] | None:
        url = f"https://api.github.com/repos/{full_name}"
        resp = self.client.get(url, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RuntimeError(f"{classify_http_error(resp.status_code)} {resp.status_code}")
        return json.loads(resp.text)

    def _fetch_readme_hash(self, full_name: str) -> str | None:
        url = f"https://api.github.com/repos/{full_name}/readme"
        resp = self.client.get(
            url,
            headers={"Accept": "application/vnd.github.raw"},
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RuntimeError(f"readme {classify_http_error(resp.status_code)}")
        return _readme_hash(resp.text[:200_000])

    def _fetch_latest_release(self, full_name: str) -> str | None:
        url = f"https://api.github.com/repos/{full_name}/releases/latest"
        resp = self.client.get(url, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise RuntimeError(f"release {classify_http_error(resp.status_code)}")
        data = json.loads(resp.text)
        return data.get("tag_name")

    def _to_resource(self, item: dict[str, Any]) -> Resource:
        now = utc_now()
        repo_id = int(item["id"])
        full_name = item.get("full_name") or ""
        html_url = item.get("html_url") or f"https://github.com/{full_name}"
        published = parse_flexible_date(item.get("created_at"), source="github.created_at")
        desc = item.get("description") or ""
        title = full_name or item.get("name") or html_url
        body = f"{title}\n{desc}\n{html_url}"
        is_official = full_name.lower().startswith("typesafe-ai/")
        return Resource(
            id=github_entity_id(repo_id),
            resource_kind=ResourceKind.SDK if is_official else ResourceKind.OTHER,
            canonical_url=normalize_url(html_url),
            source_identity=f"github:{repo_id}",
            author_or_org=(full_name.split("/")[0] if "/" in full_name else None),
            official_status=OfficialStatus.OFFICIAL if is_official else OfficialStatus.UNKNOWN,
            jev_relationship=JevRelationship.OFFICIAL if is_official else JevRelationship.UNCLEAR,
            original_title=title,
            summary_en=desc or None,
            published_at=published if published.value else FlexibleDate(),
            first_discovered_at=now,
            editorial_status=EditorialStatus.PENDING,
            verification_level=VerificationLevel.DISCOVERED,
            content_hash=content_hash(body),
            github_repo_id=repo_id,
            github_full_name=full_name,
            tags=list(item.get("topics") or []),
            license_identifier=(
                (item.get("license") or {}).get("spdx_id")
                if isinstance(item.get("license"), dict)
                else None
            ),
        )
