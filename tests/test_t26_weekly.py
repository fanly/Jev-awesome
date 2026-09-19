"""T26: weekly timezone boundaries, idempotent rerun, curated isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from jev_awesome.models import CatalogEvent, EditorialStatus
from jev_awesome.rendering.weekly import build_weekly, previous_complete_week, write_weekly
from jev_awesome.store import CatalogStore
from tests.helpers import make_resource

TZ = "Asia/Shanghai"


def test_t26_previous_week_local_not_utc():
    # Sunday evening and Monday midnight select different previous weeks
    sun = datetime(2026, 9, 13, 23, 30, tzinfo=ZoneInfo(TZ))
    mon = datetime(2026, 9, 14, 0, 30, tzinfo=ZoneInfo(TZ))
    s1, e1, id1 = previous_complete_week(sun, TZ)
    s2, e2, id2 = previous_complete_week(mon, TZ)
    assert id1 != id2
    assert e1 == s2  # adjacent weeks abut
    assert s1 < e1 == s2 < e2
    # UTC instant that is still Sunday evening in Shanghai must use local week
    utc_still_sunday = datetime(2026, 9, 13, 15, 0, tzinfo=UTC)  # 23:00 CST
    _s, _e, id_local = previous_complete_week(utc_still_sunday, TZ)
    assert id_local == id1


def test_t26_same_week_stable_id_later_rerun():
    tue = datetime(2026, 9, 15, 10, 0, tzinfo=ZoneInfo(TZ))
    wed = datetime(2026, 9, 16, 22, 0, tzinfo=ZoneInfo(TZ))
    _, _, a = previous_complete_week(tue, TZ)
    _, _, b = previous_complete_week(wed, TZ)
    assert a == b


def test_t26_boundary_event_half_open(store):
    start, end, week_id = previous_complete_week(
        datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ)), TZ
    )
    curated = make_resource(
        id="github:w1",
        editorial_status=EditorialStatus.CURATED,
        summary_zh="已采纳",
        jev_role="角色",
        developer_value="价值",
    )
    store.save_resource(curated, inbox=False)
    # Exactly at start → included
    store.save_event(
        CatalogEvent(
            id="evt-start",
            event_type="human_accepted",
            resource_id="github:w1",
            occurred_at=start,
            summary="at start",
            material=True,
        )
    )
    # Exactly at end → next week
    store.save_event(
        CatalogEvent(
            id="evt-end",
            event_type="human_accepted",
            resource_id="github:w1",
            occurred_at=end,
            summary="at end",
            material=True,
        )
    )
    wid, body, material = build_weekly(
        store, tz_name=TZ, now=datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ))
    )
    assert wid == week_id
    assert material is True
    assert "evt-start" in body
    assert "evt-end" not in body


def test_t26_idempotent_write_and_no_empty_spam(store, tmp_paths):
    curated = make_resource(
        id="github:w2",
        editorial_status=EditorialStatus.CURATED,
        summary_zh="已采纳",
        jev_role="角色",
        developer_value="价值",
    )
    store.save_resource(curated, inbox=False)
    start, _end, _wid = previous_complete_week(
        datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ)), TZ
    )
    store.save_event(
        CatalogEvent(
            id="evt-acc",
            event_type="human_accepted",
            resource_id="github:w2",
            occurred_at=start.replace(hour=12),
            summary="accepted",
            material=True,
        )
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ))
    p1 = write_weekly(store, tmp_paths, tz_name=TZ, now=now)
    assert p1 is not None and p1.exists()
    text1 = p1.read_text(encoding="utf-8")
    p2 = write_weekly(store, tmp_paths, tz_name=TZ, now=now)
    assert p2 is not None and p2 == p1
    assert p2.read_text(encoding="utf-8") == text1

    # Empty store week: do not create a new empty weekly; leave history
    history = tmp_paths.updates / "weekly-2099-W01.md"
    history.write_text("# old\n", encoding="utf-8")
    empty_store = CatalogStore(tmp_paths)
    # Use a far future "now" whose previous week has no events and no file yet
    far = datetime(2026, 10, 6, 12, 0, tzinfo=ZoneInfo(TZ))
    out = write_weekly(empty_store, tmp_paths, tz_name=TZ, now=far)
    assert out is None
    assert history.read_text(encoding="utf-8") == "# old\n"


def test_t26_pending_not_in_weekly(store):
    pending = make_resource(id="github:pend", editorial_status=EditorialStatus.PENDING)
    store.save_resource(pending, inbox=True)
    start, _, _ = previous_complete_week(datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ)), TZ)
    store.save_event(
        CatalogEvent(
            id="evt-disc",
            event_type="first_discovered",
            resource_id="github:pend",
            occurred_at=start.replace(hour=8),
            summary="discovered pending",
            material=True,
        )
    )
    _wid, body, material = build_weekly(
        store, tz_name=TZ, now=datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ))
    )
    assert material is False
    assert "evt-disc" not in body
    assert "github:pend" not in body


def test_t26_cli_write_weekly(tmp_paths, monkeypatch):
    """Production write_weekly via temp catalog root (CLI path function)."""
    from jev_awesome.rendering.weekly import write_weekly as prod_write

    store = CatalogStore(tmp_paths)
    curated = make_resource(
        id="github:cli1",
        editorial_status=EditorialStatus.CURATED,
        summary_zh="摘要",
        jev_role="角色",
        developer_value="价值",
    )
    store.save_resource(curated, inbox=False)
    start, _, _ = previous_complete_week(datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ)), TZ)
    store.save_event(
        CatalogEvent(
            id="evt-cli",
            event_type="human_accepted",
            resource_id="github:cli1",
            occurred_at=start.replace(hour=9),
            summary="cli accept",
            material=True,
        )
    )
    path = prod_write(
        store,
        tmp_paths,
        tz_name=TZ,
        now=datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo(TZ)),
    )
    assert path is not None
    assert "evt-cli" in path.read_text(encoding="utf-8")
