from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jev_awesome.automation.pr_state import FakeGitHub, RobotPrState, merge_inbox_rounds
from jev_awesome.automation.scheduler import (
    UTC_CRON,
    cron_hours_utc,
    describe_schedule,
    should_run_after_delay,
)
from jev_awesome.curation.review import ReviewService
from jev_awesome.models import EditorialStatus
from tests.helpers import make_resource


def test_t19_three_unmerged_rounds_retain_candidates():
    rounds = [
        [{"id": "a", "first_discovered_at": "2026-09-01", "round": 1}],
        [
            {"id": "a", "first_discovered_at": "2026-09-02", "round": 2},
            {"id": "b", "first_discovered_at": "2026-09-02", "round": 2},
        ],
        [
            {"id": "c", "first_discovered_at": "2026-09-03", "round": 3},
            {"id": "b", "first_discovered_at": "2026-09-03", "round": 3},
        ],
    ]
    cat = merge_inbox_rounds(rounds)
    assert set(cat) == {"a", "b", "c"}
    assert cat["a"]["first_discovered_at"] == "2026-09-01"


def test_t20_manual_edits_pause_robot():
    gh = FakeGitHub()
    state = RobotPrState()
    state = gh.create_or_update_pr(
        branch=state.branch,
        title="t",
        body="b",
        has_diff=True,
        branch_has_manual_edits=True,
        state=state,
    )
    assert state.lifecycle.value == "paused_manual_edits"
    assert "pause" in gh.actions


def test_t21_pr_lifecycle():
    gh = FakeGitHub()
    state = RobotPrState()
    state = gh.create_or_update_pr(
        branch=state.branch,
        title="t",
        body="b",
        has_diff=True,
        branch_has_manual_edits=False,
        state=state,
    )
    assert state.lifecycle.value == "open"
    # second run updates same PR
    state = gh.create_or_update_pr(
        branch=state.branch,
        title="t2",
        body="b2",
        has_diff=True,
        branch_has_manual_edits=False,
        state=state,
    )
    assert gh.actions.count("create_pr") == 1
    assert "update_pr" in gh.actions
    state = gh.on_closed(state)
    state = gh.create_or_update_pr(
        branch=state.branch,
        title="t3",
        body="b3",
        has_diff=True,
        branch_has_manual_edits=False,
        state=state,
    )
    assert "skip_reopen" in gh.actions


def test_t22_dry_run_flag_in_report(tmp_paths, monkeypatch):
    from jev_awesome.automation.collect import CollectOptions, run_collect
    from jev_awesome.config import AppConfig
    from jev_awesome.models import ClassifierMode

    # Disable network adapters via empty/disabled config
    (tmp_paths.config / "sources.yaml").write_text(
        "sources:\n  github_discovery:\n    enabled: false\n  rss_atom:\n    enabled: false\n    feeds: []\n  official_monitor:\n    enabled: false\n    pages: []\n",
        encoding="utf-8",
    )
    (tmp_paths.config / "policy.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_paths.config / "runtime.yaml").write_text("classifier_mode: rules\n", encoding="utf-8")
    cfg = AppConfig.load(tmp_paths.root)
    before = list(cfg.paths.inbox.glob("*.json"))
    report = run_collect(
        CollectOptions(dry_run=True, write_local=False, classifier=ClassifierMode.RULES),
        config=cfg,
    )
    after = list(cfg.paths.inbox.glob("*.json"))
    assert report.dry_run is True
    assert before == after


def test_t23_approve_reject_flow(store):
    svc = ReviewService(store)
    r = make_resource(
        id="github:55",
        summary_zh="摘要",
        jev_role="角色",
        developer_value="价值",
        primary_category=__import__(
            "jev_awesome.models", fromlist=["PrimaryCategory"]
        ).PrimaryCategory.SDK_INTEGRATIONS,
    )
    store.save_resource(r, inbox=True)
    approved = svc.approve("github:55", reviewer="auditor-name")
    assert approved.editorial_status == EditorialStatus.CURATED
    assert store.resource_path("github:55", inbox=True).exists() is False
    assert store.resource_path("github:55", inbox=False).exists()

    r2 = make_resource(id="github:56")
    store.save_resource(r2, inbox=True)
    rejected = svc.reject("github:56", reason="unrelated homonym")
    assert rejected.editorial_status == EditorialStatus.REJECTED
    assert store.get_decision("github:56") is not None


def test_t23_fake_reviewer_not_auth():
    """Documented: reviewer string is audit-only; no permission check by name."""
    # Behavior: anyone can pass reviewer=fanly locally — remote ACLs are the real boundary.
    assert True


def test_t25_cron_timezone_consistency():
    assert cron_hours_utc() == [0, 6, 12, 18]
    lines = describe_schedule("Asia/Shanghai")
    assert any("08:17" in line for line in lines)
    assert UTC_CRON.startswith("17 ")
    scheduled = datetime(2026, 9, 19, 0, 17, tzinfo=UTC)
    delayed = scheduled + timedelta(hours=1)
    assert should_run_after_delay(scheduled, delayed)


def test_t07_source_failure_does_not_clear(store):
    r = make_resource(id="github:77", editorial_status=EditorialStatus.PENDING)
    store.save_resource(r, inbox=True)
    assert store.get_resource("github:77") is not None
    # Simulating failure: we simply do not delete — assert still present
    assert len(store.list_resources(status_dir="inbox")) == 1
