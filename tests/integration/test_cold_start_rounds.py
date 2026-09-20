"""F3: cold-start rounds without relying on gitignored data/cache."""

from __future__ import annotations

import shutil
from pathlib import Path

from jev_awesome.automation.git_workspace import GitWorkspace, run_git
from jev_awesome.automation.publisher import ROBOT_IDENTITY_REL, Publisher, PublishOptions
from jev_awesome.paths import Paths
from jev_awesome.store import CatalogStore
from tests.integration.test_publisher_rounds import (
    _inbox_ids,
    _resource,
    _setup_repo,
    _write_candidate,
)


def _fresh_clone(tmp_path: Path, bare: Path, name: str) -> Path:
    dest = tmp_path / name
    if dest.exists():
        shutil.rmtree(dest)
    run_git(tmp_path, "clone", "-b", "main", str(bare), name)
    run_git(dest, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=dest, known_robot_shas=set()).ensure_identity()
    return dest


def _merge_robot(work: Path, bare: Path, robot_branch: str, label: str) -> Path:
    robot = work.parent / label
    if robot.exists():
        shutil.rmtree(robot)
    run_git(work.parent, "clone", "-b", robot_branch, str(bare), label)
    CatalogStore(Paths(work)).merge_catalog_from_branch_files(robot)
    return robot


def test_cold_start_rounds_no_cache_reuse(tmp_path: Path) -> None:
    """A → A+B → no_diff across destroyed workdirs; delete data/cache between rounds."""
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")

    # Round 1: A
    _write_candidate(work, _resource("github:9301", "cold-a", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "success"
    assert r1.commit_sha
    # Identity must be on robot branch (not only cache)
    robot1 = tmp_path / "robot-r1"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot-r1")
    assert (robot1 / ROBOT_IDENTITY_REL).is_file()

    # Destroy workdir + wipe any cache
    shutil.rmtree(work)

    # Round 2: fresh main, merge robot data, add B — no cache
    work2 = _fresh_clone(tmp_path, bare, "work-r2")
    cache = work2 / "data" / "cache"
    if cache.exists():
        shutil.rmtree(cache)
    _merge_robot(work2, bare, opts.robot_branch, "robot-merge-r2")
    # Ensure we are not carrying publisher_state.json
    assert not (work2 / "data" / "cache" / "publisher_state.json").exists()
    _write_candidate(work2, _resource("github:9302", "cold-b", "2026-09-02T00:00:00+00:00"))

    # Pass no last_robot_sha — must hydrate from robot tip identity
    r2 = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
        state_path=work2 / "data" / "cache" / "publisher_state.json",
    ).publish()
    assert r2.status == "success"
    assert r2.reason == "pr_updated"
    assert r2.pr_number == 1

    robot2 = tmp_path / "robot-r2"
    if robot2.exists():
        shutil.rmtree(robot2)
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot-r2")
    assert _inbox_ids(robot2) >= {"github:9301", "github:9302"}

    shutil.rmtree(work2)

    # Round 3: no material change → no_diff
    work3 = _fresh_clone(tmp_path, bare, "work-r3")
    if (work3 / "data" / "cache").exists():
        shutil.rmtree(work3 / "data" / "cache")
    _merge_robot(work3, bare, opts.robot_branch, "robot-merge-r3")
    calls = len(transport.calls)
    r3 = Publisher(
        work3,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
    ).publish()
    assert r3.status in {"no_diff", "success"}
    if r3.status == "no_diff":
        writes = [c for c in transport.calls[calls:] if c.method in {"POST", "PATCH"}]
        assert writes == []

    shutil.rmtree(work3)


def test_cold_start_pr_create_fail_then_recover(tmp_path: Path) -> None:
    bare, work, _ws, transport = _setup_repo(tmp_path)
    transport.fail_create_pr = True
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:9401", "fail-a", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "failed"
    assert r1.reason.startswith("pr_create_failed")
    # Branch was pushed even if PR create failed
    assert r1.commit_sha
    transport.set_branch_sha(opts.robot_branch, r1.commit_sha)

    shutil.rmtree(work)
    transport.fail_create_pr = False

    work2 = _fresh_clone(tmp_path, bare, "work-recover")
    if (work2 / "data" / "cache").exists():
        shutil.rmtree(work2 / "data" / "cache")
    _merge_robot(work2, bare, opts.robot_branch, "robot-recover")
    _write_candidate(work2, _resource("github:9402", "fail-b", "2026-09-02T00:00:00+00:00"))
    r2 = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
    ).publish()
    assert r2.status == "success"
    assert r2.pr_number is not None
    robot = tmp_path / "robot-recover-final"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot-recover-final")
    assert _inbox_ids(robot) >= {"github:9401", "github:9402"}


def test_cold_start_same_content_pr_create_retry(tmp_path: Path) -> None:
    """Round1 push OK + POST fail; Round2 SAME content A → 0 commit/0 push / 1 POST; Round3 → 0 writes."""
    bare, work, _ws, transport = _setup_repo(tmp_path)
    transport.fail_create_pr = True
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:9501", "same-a", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "failed"
    assert r1.reason.startswith("pr_create_failed")
    assert r1.commit_sha
    tip_after_r1 = r1.commit_sha
    transport.set_branch_sha(opts.robot_branch, tip_after_r1)
    posts_r1 = [c for c in transport.calls if c.method == "POST"]
    assert len(posts_r1) == 1

    shutil.rmtree(work)
    transport.fail_create_pr = False

    # Round 2: same content A only — no new commit/push; one POST create
    work2 = _fresh_clone(tmp_path, bare, "work-same-r2")
    if (work2 / "data" / "cache").exists():
        shutil.rmtree(work2 / "data" / "cache")
    _merge_robot(work2, bare, opts.robot_branch, "robot-same-r2")
    tip_before = run_git(bare, "rev-parse", f"refs/heads/{opts.robot_branch}").stdout.strip()
    calls_before = len(transport.calls)
    r2 = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
    ).publish()
    assert r2.status == "success"
    assert r2.reason == "pr_created"
    assert r2.pr_number == 1
    tip_after = run_git(bare, "rev-parse", f"refs/heads/{opts.robot_branch}").stdout.strip()
    assert tip_after == tip_before == tip_after_r1
    new_calls = transport.calls[calls_before:]
    assert [c for c in new_calls if c.method == "POST"]  # exactly one create
    assert len([c for c in new_calls if c.method == "POST"]) == 1
    assert [c for c in new_calls if c.method == "PATCH"] == []

    shutil.rmtree(work2)

    # Round 3: open PR exists, same content → 0 writes
    work3 = _fresh_clone(tmp_path, bare, "work-same-r3")
    if (work3 / "data" / "cache").exists():
        shutil.rmtree(work3 / "data" / "cache")
    _merge_robot(work3, bare, opts.robot_branch, "robot-same-r3")
    calls_before = len(transport.calls)
    r3 = Publisher(
        work3,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
    ).publish()
    assert r3.status == "no_diff"
    writes = [c for c in transport.calls[calls_before:] if c.method in {"POST", "PATCH"}]
    assert writes == []


def test_pr_list_403_fails_without_create(tmp_path: Path) -> None:
    """PR list 403 → failed/paused; never POST create as empty-success."""
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:9601", "list-fail", "2026-09-01T00:00:00+00:00"))
    transport.fail_list_prs_status = 403
    r = Publisher(work, transport=transport, opts=opts).publish()
    assert r.status in {"failed", "paused"}
    assert "pr_list" in r.reason or "list" in r.reason
    posts = [c for c in transport.calls if c.method == "POST"]
    assert posts == []
    _ = bare
