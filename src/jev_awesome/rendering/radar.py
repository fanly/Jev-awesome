"""Jev ecosystem radar — deterministic markdown for docs/radar/latest.md."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from jev_awesome.models import (
    CatalogEvent,
    EditorialStatus,
    JevRelationship,
    OfficialStatus,
    Resource,
    ResourceKind,
)
from jev_awesome.paths import Paths
from jev_awesome.security import escape_md, safe_href
from jev_awesome.store import CatalogStore

AUTO_DISCOVERY_LABEL = "自动发现 · 未精选"

# Sort priority: official > curated material > high-confidence new > SDK > integration > benchmark > weak
_PRIORITY = {
    "official": 0,
    "curated_material": 1,
    "high_confidence": 2,
    "sdk": 3,
    "integration": 4,
    "benchmark": 5,
    "weak": 6,
}


@dataclass(frozen=True)
class RadarEntry:
    name: str
    link: str
    date: str
    relationship: str
    why_matched: str
    source: str
    verification: str
    review_status: str
    section: str
    priority: int
    auto_discovery: bool

    def sort_key(self) -> tuple:
        return (self.priority, self.name.lower(), self.link)


def _date_str(r: Resource) -> str:
    """Deterministic date — ignore checked_at / run_id; prefer published day or first_discovered date-only."""
    if r.published_at and r.published_at.value is not None:
        v = r.published_at.value
        if isinstance(v, datetime):
            return v.date().isoformat()
        return v.isoformat()
    # Date-only from first_discovered (strip time for stability across reruns same day)
    return r.first_discovered_at.date().isoformat()


def _is_strong_signal(r: Resource) -> bool:
    blob = " ".join(
        filter(
            None,
            [
                r.original_title,
                r.summary_en,
                r.canonical_url,
                r.github_full_name or "",
                " ".join(r.tags),
            ],
        )
    ).lower()
    strong = (
        "typesafe.ai",
        "api.typesafe.ai",
        "typesafe_api_key",
        "@typesafe-ai/sdk",
        "typesafe-sdk",
        "jev-latest",
        "system one",
        "system_one",
    )
    return any(s in blob for s in strong) or (
        r.suggestion and (r.suggestion.priority_score or 0) >= 2.5
    )


def _is_weak_name_only_jev(r: Resource) -> bool:
    blob = " ".join(
        filter(None, [r.original_title, r.summary_en or "", r.github_full_name or ""])
    ).lower()
    has_jev = "jev" in blob
    has_typesafe = "typesafe" in blob or "system one" in blob or "system_one" in blob
    return has_jev and not has_typesafe and not _is_strong_signal(r)


def _bucket(r: Resource, *, curated_changed_ids: set[str]) -> tuple[str, int]:
    if (
        r.official_status == OfficialStatus.OFFICIAL
        or r.jev_relationship == JevRelationship.OFFICIAL
    ):
        return "official", _PRIORITY["official"]
    if r.id in curated_changed_ids:
        return "curated_material", _PRIORITY["curated_material"]
    if r.resource_kind == ResourceKind.SDK or (
        r.primary_category and r.primary_category.value == "sdk_integrations"
    ):
        return "sdk", _PRIORITY["sdk"]
    if r.resource_kind == ResourceKind.EVALUATION or (
        r.primary_category and r.primary_category.value == "evals_limits"
    ):
        return "benchmark", _PRIORITY["benchmark"]
    if r.resource_kind in {ResourceKind.APPLICATION, ResourceKind.TUTORIAL}:
        return "integration", _PRIORITY["integration"]
    if _is_strong_signal(r) and r.editorial_status != EditorialStatus.CURATED:
        return "high_confidence", _PRIORITY["high_confidence"]
    if _is_weak_name_only_jev(r):
        return "weak", _PRIORITY["weak"]
    if r.editorial_status in {EditorialStatus.PENDING, EditorialStatus.PROPOSED}:
        return "weak", _PRIORITY["weak"]
    return "integration", _PRIORITY["integration"]


def _entry_from_resource(
    r: Resource,
    *,
    curated_changed_ids: set[str],
    source_hint: str | None = None,
) -> RadarEntry:
    section, priority = _bucket(r, curated_changed_ids=curated_changed_ids)
    auto = r.editorial_status != EditorialStatus.CURATED
    why = []
    if r.suggestion and r.suggestion.reason_codes:
        why.extend(r.suggestion.reason_codes[:3])
    if r.official_status == OfficialStatus.OFFICIAL:
        why.append("official_status")
    if _is_strong_signal(r):
        why.append("strong_signal")
    if not why:
        why.append("catalog_presence")
    return RadarEntry(
        name=r.original_title,
        link=r.canonical_url,
        date=_date_str(r),
        relationship=r.jev_relationship.value,
        why_matched=", ".join(why),
        source=source_hint or (r.source_identity or r.id),
        verification=r.verification_level.value,
        review_status=r.editorial_status.value,
        section=section,
        priority=priority,
        auto_discovery=auto,
    )


SECTION_TITLES = [
    ("official", "Official updates"),
    ("high_confidence", "New high-confidence discoveries"),
    ("sdk", "SDK/releases"),
    ("curated_material", "Curated projects changed"),
    ("benchmark", "Research/benchmarks"),
    ("needs_review", "Needs review"),
    ("coverage", "Coverage notes"),
]


def build_radar_entries(
    store: CatalogStore,
    *,
    events: Iterable[CatalogEvent] | None = None,
) -> list[RadarEntry]:
    curated = [
        r
        for r in store.list_resources(status_dir="resources")
        if r.editorial_status == EditorialStatus.CURATED
    ]
    inbox = store.list_resources(status_dir="inbox")
    events = list(events if events is not None else store.list_events())
    curated_changed_ids = {
        e.resource_id
        for e in events
        if e.material
        and e.event_type in {"new_version", "doc_change", "archived", "verification_update"}
        and e.resource_id in {c.id for c in curated}
    }

    entries: list[RadarEntry] = []
    for r in curated:
        entries.append(
            _entry_from_resource(r, curated_changed_ids=curated_changed_ids, source_hint="curated")
        )
    for r in inbox:
        # Skip stars-only noise: weak name-only still appears under needs_review, not high radar
        entries.append(
            _entry_from_resource(r, curated_changed_ids=curated_changed_ids, source_hint="inbox")
        )
    return entries


def render_radar_markdown(
    store: CatalogStore | None = None,
    *,
    coverage_notes: list[str] | None = None,
) -> str:
    store = store or CatalogStore()
    entries = build_radar_entries(store)
    by_section: dict[str, list[RadarEntry]] = {k: [] for k, _ in SECTION_TITLES}

    for e in entries:
        if e.section == "official":
            by_section["official"].append(e)
        elif e.section == "curated_material":
            by_section["curated_material"].append(e)
        elif e.section == "high_confidence":
            by_section["high_confidence"].append(e)
        elif e.section == "sdk":
            by_section["sdk"].append(e)
        elif e.section == "benchmark":
            by_section["benchmark"].append(e)
        elif e.section in {"weak", "integration"} and e.auto_discovery:
            by_section["needs_review"].append(e)
        elif e.section == "integration" and not e.auto_discovery:
            by_section["curated_material"].append(e)
        else:
            by_section["needs_review"].append(e)

    for key in by_section:
        by_section[key] = sorted(by_section[key], key=lambda e: e.sort_key())

    notes = list(coverage_notes or [])
    if not notes:
        notes.append(
            "Radar is generated from local catalog only; live GitHub coverage is reported in collect run reports."
        )
        notes.append("Stars-only observations are omitted from material sections.")
        notes.append(
            "Deterministic: same catalog → same body (ignores checked_at / run_id / stars-only)."
        )

    lines = [
        "# Jev 生态雷达",
        "",
        "本页由 `jev-awesome render` 生成。自动发现条目标为 **"
        + AUTO_DISCOVERY_LABEL
        + "**，不代表编辑精选。",
        "",
    ]
    for key, title in SECTION_TITLES:
        lines.append(f"## {title}")
        lines.append("")
        if key == "coverage":
            for n in notes:
                lines.append(f"- {n}")
            lines.append("")
            continue
        items = by_section.get(key) or []
        if not items:
            lines.append("_（本轮无条目）_")
            lines.append("")
            continue
        for e in items:
            badge = f" · `{AUTO_DISCOVERY_LABEL}`" if e.auto_discovery else ""
            lines.append(
                f"- **[{escape_md(e.name)}]({safe_href(e.link)})**{badge}  \n"
                f"  日期 `{e.date}` · 关系建议 `{e.relationship}` · 匹配原因 `{e.why_matched}`  \n"
                f"  来源 `{e.source}` · 验证 `{e.verification}` · 审阅 `{e.review_status}`"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def radar_highlights(store: CatalogStore | None = None, *, limit: int = 5) -> list[RadarEntry]:
    """Top 3–5 material changes for README — never dump pending queue."""
    store = store or CatalogStore()
    entries = build_radar_entries(store)
    material = [
        e
        for e in entries
        if e.section in {"official", "curated_material", "high_confidence", "sdk"}
        or (e.section == "benchmark" and not e.auto_discovery)
    ]
    material.sort(key=lambda e: e.sort_key())
    # Prefer non-auto first within same priority already handled; cap
    return material[:limit]


def write_radar(store: CatalogStore | None = None, paths: Paths | None = None) -> str:
    from jev_awesome.atomic_io import atomic_write_text

    store = store or CatalogStore()
    paths = paths or store.paths
    out_dir = paths.docs / "radar"
    out_dir.mkdir(parents=True, exist_ok=True)
    body = render_radar_markdown(store)
    path = out_dir / "latest.md"
    atomic_write_text(path, body)
    return body
