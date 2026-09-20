"""A09–A18 / A28–A29: planner, radar, curated preservation, awesome radar."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from jev_awesome.automation.source_planner import (
    PlanStatus,
    SourceCheckpointStore,
    parse_frequency,
    plan_source,
)
from jev_awesome.curation.editorial_hash import curated_editorial_snapshot, editorial_fingerprint
from jev_awesome.models import EditorialStatus, OfficialStatus, ResourceKind
from jev_awesome.rendering.radar import AUTO_DISCOVERY_LABEL, render_radar_markdown
from jev_awesome.sources.awesome import assert_no_copied_summary, extract_candidate_urls
from jev_awesome.sources.github import GitHubDiscoveryAdapter, normalize_queries
from jev_awesome.sources.http_client import HttpResponse, SafeHttpClient
from jev_awesome.sources.known_repos import merge_watchlist
from jev_awesome.store import CatalogStore
from tests.helpers import make_resource

# --- A09 / A10: frequency parse + due / not_due ---


def test_a09_parse_frequency_units():
    assert parse_frequency("6h") == timedelta(hours=6)
    assert parse_frequency("1d") == timedelta(days=1)
    assert parse_frequency("7d") == timedelta(days=7)
    assert parse_frequency("2w") == timedelta(weeks=2)


def test_a10_planner_due_and_not_due():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=7)
    due = plan_source(now=now, frequency="6h", last_successful_at=last, mode="incremental")
    assert due.status == PlanStatus.DUE
    assert due.should_run

    recent = now - timedelta(hours=2)
    not_due = plan_source(now=now, frequency="6h", last_successful_at=recent, mode="incremental")
    assert not_due.status == PlanStatus.NOT_DUE
    assert not not_due.should_run


def test_a11_planner_force_and_backfill_and_modes():
    now = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    recent = now - timedelta(hours=1)
    forced = plan_source(
        now=now, frequency="6h", last_successful_at=recent, mode="incremental", force=True
    )
    assert forced.status == PlanStatus.FORCED

    backfill = plan_source(now=now, frequency="1d", last_successful_at=None, mode="incremental")
    assert backfill.status == PlanStatus.BACKFILL

    refresh = plan_source(
        now=now, frequency="6h", last_successful_at=recent, mode="refresh", force=False
    )
    assert refresh.status == PlanStatus.DUE
    assert refresh.should_run

    all_mode = plan_source(now=now, frequency="6h", last_successful_at=recent, mode="all")
    assert all_mode.should_run


def test_a12_checkpoint_not_advanced_on_dry_run(tmp_path: Path):
    store = SourceCheckpointStore(tmp_path / "source_checkpoints.json")
    assert (
        store.record_success("github_discovery", dry_run=True, coverage_status="complete") is None
    )
    assert store.last_successful_at("github_discovery") is None
    path = store.record_success("github_discovery", dry_run=False, coverage_status="complete")
    assert path is not None and path.exists()
    assert store.last_successful_at("github_discovery") is not None


def test_a13_checkpoint_not_advanced_on_failure_semantics(tmp_path: Path):
    """Caller must not call record_success on failure — store itself only writes when asked."""
    store = SourceCheckpointStore(tmp_path / "source_checkpoints.json")
    # Simulating failure: never call record_success
    assert store.load() == {}
    # Success path
    store.record_success("rss_atom", dry_run=False, coverage_status="partial")
    assert "rss_atom" in store.load()


def test_a14_github_query_metadata_and_search_cap():
    qs = normalize_queries(
        [
            {"id": "gh-broad-jev", "query": "jev in:name fork:false", "priority": 90},
            '"typesafe.ai" in:readme fork:false',
        ]
    )
    assert qs[0]["id"] == "gh-broad-jev"
    assert qs[0]["priority"] == 90
    assert qs[1]["id"] == "gh-q1"

    class Scripted(SafeHttpClient):
        def __init__(self, responses):
            super().__init__(allowed_domains={"api.github.com", "github.com"})
            self._responses = list(responses)
            self.request_count = 0

        def get(self, url: str, **kwargs):  # type: ignore[override]
            self.request_count += 1
            return self._responses.pop(0)

    items = [
        {
            "id": i,
            "full_name": f"org/r{i}",
            "html_url": f"https://github.com/org/r{i}",
            "description": "typesafe.ai",
            "created_at": "2024-01-01T00:00:00Z",
        }
        for i in range(1, 31)
    ]
    payload = json.dumps({"total_count": 2500, "incomplete_results": False, "items": items})
    client = Scripted([HttpResponse(200, {}, payload, "https://api.github.com")])
    adapter = GitHubDiscoveryAdapter(
        queries=[{"id": "gh-cap", "query": "topic:jev", "priority": 1}], client=client
    )
    from jev_awesome.sources import CollectContext

    _, result = adapter.collect(
        CollectContext(dry_run=True, write_local=False, max_pages=1, per_page=30)
    )
    assert result.coverage_status == "partial"
    assert result.queries[0].query_id == "gh-cap"
    assert result.queries[0].gap_reason in {"page_budget", "search_cap"}
    # Must never claim complete from page budget alone when more results exist
    assert result.queries[0].coverage_status != "complete"


def test_a15_known_repo_watchlist_merges_curated():
    curated = [
        make_resource(
            id="github:1",
            editorial_status=EditorialStatus.CURATED,
            github_full_name="browser-use/jev-ultrafast",
            canonical_url="https://github.com/browser-use/jev-ultrafast",
        ),
        make_resource(
            id="github:2",
            editorial_status=EditorialStatus.PENDING,
            github_full_name="someone/pending-only",
            canonical_url="https://github.com/someone/pending-only",
        ),
    ]
    merged = merge_watchlist(
        [{"full_name": "typesafe-ai/typesafe-sdk-python"}],
        curated,
    )
    names = {m["full_name"] for m in merged}
    assert "typesafe-ai/typesafe-sdk-python" in names
    assert "browser-use/jev-ultrafast" in names
    assert "someone/pending-only" not in names


def test_a16_awesome_extracts_links_not_summaries():
    md = """
# Awesome

- [pg-jev](https://github.com/realZachi/pg-jev) 官方推荐 · 精选排名第一 ⭐⭐⭐
- [LocalJev](https://github.com/githubnext/localjev) 强烈推荐必看
"""
    urls = extract_candidate_urls(md)
    assert "https://github.com/realZachi/pg-jev" in urls
    assert "https://github.com/githubnext/localjev" in urls
    r = make_resource(
        id="web:x",
        canonical_url="https://github.com/realZachi/pg-jev",
        original_title="realZachi/pg-jev",
        summary_zh=None,
        summary_en=None,
        developer_value=None,
    )
    assert_no_copied_summary(r, md)
    # Would fail if we copied ranking blurbs
    bad = r.model_copy(update={"summary_zh": "官方推荐 · 精选排名第一"})
    try:
        assert_no_copied_summary(bad, md)
        raised = False
    except AssertionError:
        raised = True
    assert raised


def test_a17_radar_deterministic(store):
    store.save_resource(
        make_resource(
            id="github:rad1",
            editorial_status=EditorialStatus.CURATED,
            official_status=OfficialStatus.OFFICIAL,
            original_title="typesafe-ai/typesafe-sdk-python",
            canonical_url="https://github.com/typesafe-ai/typesafe-sdk-python",
            summary_zh="官方 SDK",
            jev_role="角色",
            developer_value="价值",
            resource_kind=ResourceKind.SDK,
        ),
        inbox=False,
    )
    store.save_resource(
        make_resource(
            id="github:rad2",
            editorial_status=EditorialStatus.PENDING,
            original_title="acme/jev-toy",
            canonical_url="https://github.com/acme/jev-toy",
            summary_en="a jev named toy",
        ),
        inbox=True,
    )
    a = render_radar_markdown(store)
    b = render_radar_markdown(store)
    assert a == b
    assert AUTO_DISCOVERY_LABEL in a
    assert "Official updates" in a
    assert "Needs review" in a


def test_a18_curated_editorial_fingerprint_stable(tmp_path: Path):
    from jev_awesome.paths import Paths

    paths = Paths(tmp_path)
    paths.ensure_data_dirs()
    store = CatalogStore(paths)
    r = make_resource(
        id="github:cur1",
        editorial_status=EditorialStatus.CURATED,
        summary_zh="人工摘要",
        developer_value="价值",
        jev_role="角色",
        limitations="限制",
    )
    store.save_resource(r, inbox=False)
    snap1 = curated_editorial_snapshot(paths.resources)
    snap2 = curated_editorial_snapshot(paths.resources)
    assert snap1 == snap2
    assert snap1["github:cur1"] == editorial_fingerprint(r)


def test_a28_weak_name_only_jev_low_priority():
    from jev_awesome.classification.rules import RulesClassifier

    c = RulesClassifier()
    weak = c.classify(
        make_resource(
            original_title="acme/jev-utils",
            canonical_url="https://github.com/acme/jev-utils",
            summary_en="utilities named jev",
        )
    )
    assert "weak_name_only_jev" in weak.reason_codes
    assert (weak.priority_score or 0) <= 1.0

    strong = c.classify(
        make_resource(
            original_title="acme/demo",
            canonical_url="https://github.com/acme/demo",
            summary_en="uses typesafe-sdk and TYPESAFE_API_KEY",
        )
    )
    assert any("strong" in x for x in strong.reason_codes)
    assert (strong.priority_score or 0) >= 2.0


def test_a29_planner_dry_run_flag_documented_no_write(tmp_path: Path):
    now = datetime(2026, 9, 20, tzinfo=UTC)
    d = plan_source(
        now=now,
        frequency="6h",
        last_successful_at=None,
        mode="incremental",
        dry_run=True,
    )
    assert d.status == PlanStatus.BACKFILL
    cps = SourceCheckpointStore(tmp_path / "cps.json")
    # dry_run decision must not imply persistence
    assert cps.record_success("x", dry_run=True) is None
