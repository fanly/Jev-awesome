from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.models import EditorialStatus
from jev_awesome.paths import Paths
from jev_awesome.store import CatalogStore

# Events that may appear in the curated weekly digest
_WEEKLY_EVENT_TYPES = frozenset(
    {
        "human_accepted",
        "new_version",
        "doc_change",
        "verification_update",
        "withdrawn",
        "archived",
    }
)


def previous_complete_week(
    now: datetime | None = None, tz_name: str = "Asia/Shanghai"
) -> tuple[datetime, datetime, str]:
    """Return [start, end) of previous complete local week (Mon 00:00 – next Mon)."""
    tz = ZoneInfo(tz_name)
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    # Start of this week (Monday)
    days_since_mon = now_local.weekday()
    this_monday = (now_local - timedelta(days=days_since_mon)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    prev_monday = this_monday - timedelta(days=7)
    # Stable week id from local Monday (not UTC week)
    week_id = f"{prev_monday.strftime('%G')}-W{prev_monday.strftime('%V')}"
    return prev_monday, this_monday, week_id


def build_weekly(
    store: CatalogStore | None = None,
    *,
    tz_name: str = "Asia/Shanghai",
    now: datetime | None = None,
) -> tuple[str, str, bool]:
    """Return (week_id, markdown, material_changed). Idempotent for same events."""
    store = store or CatalogStore()
    start, end, week_id = previous_complete_week(now, tz_name)
    curated_ids = {
        r.id
        for r in store.list_resources(status_dir="resources")
        if r.editorial_status == EditorialStatus.CURATED
    }
    # Also treat human_accepted events as allowlisted even if resource scan races
    events = []
    for e in store.list_events():
        if not e.material:
            continue
        if e.event_type not in _WEEKLY_EVENT_TYPES:
            continue
        occurred = e.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        local_occ = occurred.astimezone(start.tzinfo)
        if not (start <= local_occ < end):
            continue
        if e.event_type == "human_accepted" or e.resource_id in curated_ids:
            events.append(e)
    events.sort(key=lambda e: (e.occurred_at, e.id))
    lines = [
        f"# 周报 {week_id}",
        "",
        f"窗口（{tz_name}）：{start.isoformat()} — {end.isoformat()}（不含结束）",
        "",
    ]
    if not events:
        lines.append("本周无已采纳内容或精选资源的实质变化。")
        lines.append("")
        material = False
    else:
        material = True
        for e in events:
            lines.append(f"- `{e.id}` **{e.event_type}** `{e.resource_id}`: {e.summary}")
        lines.append("")
    body = "\n".join(lines)
    return week_id, body, material


def write_weekly(
    store: CatalogStore | None = None,
    paths: Paths | None = None,
    *,
    tz_name: str = "Asia/Shanghai",
    now: datetime | None = None,
) -> Path | None:
    store = store or CatalogStore()
    paths = paths or store.paths
    paths.updates.mkdir(parents=True, exist_ok=True)
    week_id, body, material = build_weekly(store, tz_name=tz_name, now=now)
    out = paths.updates / f"{week_id}.md"
    prev = out.read_text(encoding="utf-8") if out.exists() else None
    if not material:
        # Do not manufacture empty weeklies; never delete existing history
        if prev is None:
            return None
        return out
    if prev == body:
        return out
    atomic_write_text(out, body)
    return out
