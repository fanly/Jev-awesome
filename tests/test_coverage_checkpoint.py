"""Coverage status + checkpoint + disposition reconciliation tests."""

from __future__ import annotations

import json

from jev_awesome.automation.checkpoint import CheckpointStore
from jev_awesome.automation.collect import CollectOptions, run_collect
from jev_awesome.config import AppConfig
from jev_awesome.models import ClassifierMode
from jev_awesome.sources import CollectContext
from jev_awesome.sources.github import GitHubDiscoveryAdapter
from jev_awesome.sources.http_client import HttpResponse, SafeHttpClient


class ScriptedClient(SafeHttpClient):
    def __init__(self, responses: list[HttpResponse]):
        super().__init__(allowed_domains={"api.github.com", "github.com"})
        self._responses = list(responses)
        self.request_count = 0

    def get(self, url: str, **kwargs):  # type: ignore[override]
        self.request_count += 1
        return self._responses.pop(0)


def _page(items: list[dict], *, total: int, incomplete: bool = False) -> HttpResponse:
    return HttpResponse(
        200,
        {},
        json.dumps({"total_count": total, "incomplete_results": incomplete, "items": items}),
        "https://api.github.com",
    )


def _item(i: int) -> dict:
    return {
        "id": i,
        "full_name": f"org/repo{i}",
        "html_url": f"https://github.com/org/repo{i}",
        "description": "jev",
        "created_at": "2024-01-01T00:00:00Z",
    }


def test_t05_page_budget_marks_partial_coverage():
    # max_pages=1 but total_count >> page size → partial + page_budget
    client = ScriptedClient([_page([_item(1), _item(2)], total=500, incomplete=False)])
    # per_page default 30 but we only return 2 — that completes. Need full page.
    items = [_item(i) for i in range(1, 31)]
    client = ScriptedClient([_page(items, total=500, incomplete=False)])
    adapter = GitHubDiscoveryAdapter(queries=["topic:jev"], client=client)
    resources, result = adapter.collect(
        CollectContext(dry_run=True, write_local=False, max_pages=1, per_page=30)
    )
    assert len(resources) == 30
    assert result.coverage_status == "partial"
    assert result.queries[0].gap_reason == "page_budget"
    assert any("page_budget" in g for g in result.coverage_gaps)


def test_t05_short_last_page_complete():
    client = ScriptedClient([_page([_item(1)], total=1, incomplete=False)])
    adapter = GitHubDiscoveryAdapter(queries=["topic:jev"], client=client)
    _, result = adapter.collect(
        CollectContext(dry_run=True, write_local=False, max_pages=2, per_page=30)
    )
    assert result.coverage_status == "complete"
    assert result.queries[0].coverage_status == "complete"


def test_t27_failed_shard_does_not_advance_checkpoint(tmp_paths):
    (tmp_paths.config / "sources.yaml").write_text(
        "sources:\n  github_discovery:\n    enabled: false\n  rss_atom:\n    enabled: false\n    feeds: []\n  official_monitor:\n    enabled: false\n    pages: []\n",
        encoding="utf-8",
    )
    (tmp_paths.config / "policy.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_paths.config / "runtime.yaml").write_text("classifier_mode: rules\n", encoding="utf-8")
    cfg = AppConfig.load(tmp_paths.root)
    # Manually test CheckpointStore gates
    cps = CheckpointStore(cfg.paths.cache / "checkpoints")
    assert (
        cps.save("s", cursor="1", coverage_status="partial", durable=False, dry_run=False) is None
    )
    assert cps.save("s", cursor="1", coverage_status="partial", durable=True, dry_run=True) is None
    path = cps.save("s", cursor="1", coverage_status="complete", durable=True, dry_run=False)
    assert path is not None and path.exists()


def test_t01_fixture_collect_idempotent_dispositions(tmp_paths, monkeypatch):
    (tmp_paths.config / "sources.yaml").write_text(
        "sources:\n  github_discovery:\n    enabled: false\n  rss_atom:\n    enabled: false\n    feeds: []\n  official_monitor:\n    enabled: false\n    pages: []\n",
        encoding="utf-8",
    )
    (tmp_paths.config / "policy.yaml").write_text("{}\n", encoding="utf-8")
    (tmp_paths.config / "runtime.yaml").write_text("classifier_mode: rules\n", encoding="utf-8")
    cfg = AppConfig.load(tmp_paths.root)
    r1 = run_collect(
        CollectOptions(dry_run=False, write_local=True, classifier=ClassifierMode.RULES),
        config=cfg,
    )
    r2 = run_collect(
        CollectOptions(dry_run=False, write_local=True, classifier=ClassifierMode.RULES),
        config=cfg,
    )
    assert r1.counts_after == r2.counts_after
    assert r1.overall == r2.overall
