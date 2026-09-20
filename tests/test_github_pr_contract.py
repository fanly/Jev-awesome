"""F4: GitHub PR HTTP contract — merged_at without merged; open+historical merged."""

from __future__ import annotations

from pathlib import Path

from jev_awesome.automation.git_workspace import GitWorkspace, run_git
from jev_awesome.automation.github_transport import (
    FakeGitHubTransport,
    normalize_pr_list_item,
    pr_is_closed_unmerged,
    pr_is_merged,
)
from jev_awesome.automation.publisher import Publisher, PublishOptions
from tests.integration.test_publisher_rounds import (
    _inbox_ids,
    _resource,
    _setup_repo,
    _write_candidate,
)


def test_pr_is_merged_via_merged_at_without_merged_field() -> None:
    pr = {"state": "closed", "merged_at": "2026-01-15T12:00:00Z"}
    assert "merged" not in pr
    assert pr_is_merged(pr) is True
    assert pr_is_closed_unmerged(pr) is False


def test_pr_is_merged_false_when_merged_at_null() -> None:
    pr = {"state": "closed", "merged_at": None}
    assert pr_is_merged(pr) is False
    assert pr_is_closed_unmerged(pr) is True


def test_pr_is_merged_true_when_merged_boolean() -> None:
    assert pr_is_merged({"merged": True, "merged_at": None}) is True


def test_normalize_list_omits_merged_boolean() -> None:
    raw = {
        "number": 1,
        "state": "closed",
        "merged": True,
        "merged_at": "2026-01-15T12:00:00Z",
        "head": {"ref": "automation/catalog-update", "sha": "abc"},
    }
    out = normalize_pr_list_item(raw)
    assert "merged" not in out
    assert out["merged_at"] == "2026-01-15T12:00:00Z"
    assert pr_is_merged(out) is True


def test_fake_list_responses_omit_merged_field() -> None:
    t = FakeGitHubTransport()
    t.pulls.append(
        {
            "number": 1,
            "state": "closed",
            "merged": True,
            "merged_at": "2026-01-15T12:00:00Z",
            "head": {"ref": "automation/catalog-update", "sha": "deadbeef"},
        }
    )
    status, data = t.get_json(
        "/repos/fanly/Jev-awesome/pulls?state=closed&head=fanly:automation/catalog-update"
        "&per_page=20&page=1"
    )
    assert status == 200
    assert isinstance(data, list) and len(data) == 1
    assert "merged" not in data[0]
    assert pr_is_merged(data[0]) is True


def test_historical_merged_plus_open_pr_continues_no_branch_delete(tmp_path: Path) -> None:
    """Open robot PR + historical merged → update open PR; do not delete branch."""
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:9101", "hist-a", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "success" and r1.pr_number == 1
    assert r1.commit_sha

    # Historical merged PR (merged_at only in list path)
    transport.mark_merged(1, head_sha=r1.commit_sha)
    # New open PR still targeting robot branch (simulates continued work after prior merge)
    transport.pulls.append(
        {
            "number": 2,
            "html_url": "https://github.com/fanly/Jev-awesome/pull/2",
            "state": "open",
            "merged": False,
            "merged_at": None,
            "head": {"ref": opts.robot_branch, "sha": r1.commit_sha},
            "base": {"ref": "main"},
        }
    )
    transport.next_pr = 3
    transport.set_branch_sha(opts.robot_branch, r1.commit_sha)

    # Prove _robot_pr_merged is false while open exists
    pub_probe = Publisher(work, transport=transport, opts=opts)
    assert pub_probe._robot_pr_merged() is False  # noqa: SLF001

    work2 = tmp_path / "work-open"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work-open")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    known = {r1.commit_sha}
    GitWorkspace(root=work2, known_robot_shas=known).ensure_identity()
    robot = tmp_path / "robot-open"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot-open")
    from jev_awesome.paths import Paths
    from jev_awesome.store import CatalogStore

    CatalogStore(Paths(work2)).merge_catalog_from_branch_files(robot)
    _write_candidate(work2, _resource("github:9102", "hist-b", "2026-09-02T00:00:00+00:00"))

    # Record branch existence before publish
    refs_before = run_git(bare, "show-ref").stdout
    assert opts.robot_branch in refs_before

    pub = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(
            enabled=True,
            dry_run=False,
            remote_name="publish-remote",
            last_robot_sha=r1.commit_sha,
        ),
    )
    pub.git.known_robot_shas = known
    result = pub.publish()
    assert result.status == "success"
    assert result.reason == "pr_updated"
    assert result.pr_number == 2

    # Branch must still exist (no delete/rebuild)
    refs_after = run_git(bare, "show-ref").stdout
    assert opts.robot_branch in refs_after
    assert len(transport.open_robot_prs(opts.robot_branch)) == 1
    robot2 = tmp_path / "robot-open2"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot-open2")
    assert _inbox_ids(robot2) >= {"github:9101", "github:9102"}


def test_publisher_uses_get_json_not_fake_helpers(tmp_path: Path) -> None:
    bare, work, _ws, transport = _setup_repo(tmp_path)

    # Shadow Fake-only helpers so getattr(..., None) would not find callables
    # if publisher incorrectly still used them.
    transport.has_merged_robot_pr = None  # type: ignore[assignment]
    transport.latest_unmerged_head_sha = None  # type: ignore[assignment]

    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:9201", "no-helper", "2026-09-01T00:00:00+00:00"))
    result = Publisher(work, transport=transport, opts=opts).publish()
    assert result.status == "success"
    assert any(c.method == "GET" and "/pulls" in c.url for c in transport.calls)
    # Prove helpers were not invoked (still None, not replaced with results)
    assert transport.has_merged_robot_pr is None
    assert transport.latest_unmerged_head_sha is None
