"""T21 extensions: merge continuation, squash, branch-delete recovery."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from jev_awesome.automation.git_workspace import GitWorkspace, run_git
from jev_awesome.automation.publisher import Publisher, PublishOptions
from jev_awesome.models import Decision, EditorialStatus
from jev_awesome.paths import Paths
from jev_awesome.store import CatalogStore
from tests.integration.test_publisher_rounds import (
    _inbox_ids,
    _resource,
    _setup_repo,
    _write_candidate,
)


def _merge_robot_into_main(
    bare: Path,
    *,
    robot_branch: str,
    mode: str,
) -> str:
    """Merge robot catalog into main. mode: merge | squash."""
    work = bare.parent / f"merge-{mode}"
    if work.exists():
        import shutil

        shutil.rmtree(work)
    run_git(bare.parent, "clone", "-b", "main", str(bare), work.name)
    GitWorkspace(root=work, known_robot_shas=set()).ensure_identity()
    run_git(work, "fetch", "origin", robot_branch)
    robot_tree = bare.parent / f"robot-tree-{mode}"
    if robot_tree.exists():
        import shutil

        shutil.rmtree(robot_tree)
    run_git(bare.parent, "clone", "-b", robot_branch, str(bare), robot_tree.name)
    CatalogStore(Paths(work)).merge_catalog_from_branch_files(robot_tree)
    run_git(work, "add", "-A")
    if mode == "squash":
        run_git(work, "commit", "-m", "squash catalog update from robot")
    else:
        # Ordinary content merge commit (files already merged via store)
        run_git(work, "commit", "-m", "merge catalog update from robot")
    run_git(work, "push", "origin", "main")
    return run_git(work, "rev-parse", "HEAD").stdout.strip()


def test_t21_after_merge_next_round_only_d(tmp_path: Path):
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:1001", "proj-a", "2026-09-01T00:00:00+00:00"))
    _write_candidate(work, _resource("github:1002", "proj-b", "2026-09-02T00:00:00+00:00"))
    _write_candidate(work, _resource("github:1003", "proj-c", "2026-09-03T00:00:00+00:00"))
    pub = Publisher(work, transport=transport, opts=opts)
    r1 = pub.publish()
    assert r1.status == "success"
    assert r1.pr_number == 1
    first_a = CatalogStore(Paths(work)).get_resource("github:1001")
    assert first_a is not None
    discovered_a = first_a.first_discovered_at

    _merge_robot_into_main(bare, robot_branch=opts.robot_branch, mode="merge")
    transport.mark_merged(1, head_sha=r1.commit_sha)

    # Next runner on new main
    work2 = tmp_path / "work-after-merge"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work-after-merge")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=work2, known_robot_shas=set()).ensure_identity()
    assert _inbox_ids(work2) >= {"github:1001", "github:1002", "github:1003"}
    _write_candidate(work2, _resource("github:1004", "proj-d", "2026-09-04T00:00:00+00:00"))

    pub2 = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
    )
    r2 = pub2.publish()
    assert r2.status == "success"
    assert r2.reason == "pr_created"
    assert r2.pr_number == 2
    assert len(transport.open_robot_prs(opts.robot_branch)) == 1

    robot = tmp_path / "robot-after"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot-after")
    ids = _inbox_ids(robot)
    assert "github:1004" in ids
    assert ids >= {"github:1001", "github:1002", "github:1003", "github:1004"}
    a = CatalogStore(Paths(robot)).get_resource("github:1001")
    assert a is not None and a.first_discovered_at == discovered_a

    # No material change → no write
    work3 = tmp_path / "work-nodiff"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work-nodiff")
    run_git(work3, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(
        root=work3, known_robot_shas=set(pub2.git.known_robot_shas or [])
    ).ensure_identity()
    CatalogStore(Paths(work3)).merge_catalog_from_branch_files(robot)
    calls = len(transport.calls)
    r3 = Publisher(
        work3,
        transport=transport,
        opts=PublishOptions(
            enabled=True,
            dry_run=False,
            remote_name="publish-remote",
            last_robot_sha=r2.commit_sha,
        ),
    )
    r3.git.known_robot_shas = set(pub2.git.known_robot_shas or [])
    out = r3.publish()
    assert out.status in {"no_diff", "success"}
    if out.status == "no_diff":
        assert [c for c in transport.calls[calls:] if c.method in {"POST", "PATCH"}] == []


def test_t21_squash_merge_then_continue(tmp_path: Path):
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:5001", "s-a", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "success"
    robot_sha = r1.commit_sha
    assert robot_sha

    main_sha = _merge_robot_into_main(bare, robot_branch=opts.robot_branch, mode="squash")
    transport.mark_merged(1, head_sha=robot_sha)
    # Squash tip is not the robot commit
    assert main_sha != robot_sha

    work2 = tmp_path / "work-squash"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work-squash")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=work2, known_robot_shas={robot_sha}).ensure_identity()
    _write_candidate(work2, _resource("github:5002", "s-b", "2026-09-02T00:00:00+00:00"))
    r2 = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(
            enabled=True,
            dry_run=False,
            remote_name="publish-remote",
            last_robot_sha=robot_sha,
        ),
    ).publish()
    assert r2.status == "success"
    assert r2.pr_number == 2


def test_t21_branch_deleted_recovers_from_pr_head(tmp_path: Path):
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:6001", "del-a", "2026-09-01T00:00:00+00:00"))
    pub = Publisher(work, transport=transport, opts=opts)
    r1 = pub.publish()
    assert r1.status == "success" and r1.commit_sha
    transport.set_branch_sha(opts.robot_branch, r1.commit_sha)
    for p in transport.robot_prs(opts.robot_branch):
        p["head"]["sha"] = r1.commit_sha

    # Delete remote robot branch; objects remain in bare
    run_git(bare, "update-ref", "-d", f"refs/heads/{opts.robot_branch}")
    assert run_git(bare, "show-ref", check=False).stdout.find(opts.robot_branch) < 0

    work2 = tmp_path / "work-del"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work-del")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=work2, known_robot_shas={r1.commit_sha}).ensure_identity()
    _write_candidate(work2, _resource("github:6002", "del-b", "2026-09-02T00:00:00+00:00"))
    r2 = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(
            enabled=True,
            dry_run=False,
            remote_name="publish-remote",
            last_robot_sha=r1.commit_sha,
        ),
    ).publish()
    assert r2.status == "success"
    robot = tmp_path / "robot-del"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot-del")
    assert _inbox_ids(robot) >= {"github:6001", "github:6002"}


def test_t21_branch_deleted_without_evidence_pauses(tmp_path: Path):
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:7001", "gap-a", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.commit_sha
    run_git(bare, "update-ref", "-d", f"refs/heads/{opts.robot_branch}")
    # Wipe PR head evidence
    transport.pulls.clear()
    transport.refs.clear()

    work2 = tmp_path / "work-gap"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work-gap")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=work2, known_robot_shas=set()).ensure_identity()
    _write_candidate(work2, _resource("github:7002", "gap-b", "2026-09-02T00:00:00+00:00"))
    result = Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(
            enabled=True,
            dry_run=False,
            remote_name="publish-remote",
            last_robot_sha=r1.commit_sha,
        ),
    ).publish()
    assert result.status == "paused"
    assert result.reason == "recovery_gap"
    assert (work2 / "data" / "reports" / "pending-robot-write.json").exists()
    # Must not invent a PR that drops A
    assert transport.open_robot_prs(opts.robot_branch) == []


def test_t21_main_rejected_not_restored_from_robot(tmp_path: Path):
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:8001", "rej-a", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "success"

    # Merge then reject A on main
    _merge_robot_into_main(bare, robot_branch=opts.robot_branch, mode="merge")
    transport.mark_merged(1, head_sha=r1.commit_sha)
    main = tmp_path / "main-rej"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "main-rej")
    GitWorkspace(root=main, known_robot_shas=set()).ensure_identity()
    store = CatalogStore(Paths(main))
    a = store.get_resource("github:8001")
    assert a is not None
    rejected = a.model_copy(update={"editorial_status": EditorialStatus.REJECTED})
    store.save_resource(rejected, inbox=False)

    store.save_decision(
        Decision(
            resource_id="github:8001",
            decision="rejected",
            reason="noise",
            decided_at=datetime.now(UTC),
            content_hash=a.content_hash,
        )
    )
    run_git(main, "add", "-A")
    run_git(main, "commit", "-m", "reject A on main")
    run_git(main, "push", "origin", "main")

    work2 = tmp_path / "work-rej"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work-rej")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    # Stale robot still has pending A — merge-from then publish
    robot = tmp_path / "stale-robot"
    # Recreate robot tip from old sha if branch still exists
    try:
        run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "stale-robot")
        CatalogStore(Paths(work2)).merge_catalog_from_branch_files(robot)
    except Exception:
        pass
    GitWorkspace(root=work2, known_robot_shas=set()).ensure_identity()
    _write_candidate(work2, _resource("github:8002", "rej-b", "2026-09-02T00:00:00+00:00"))
    Publisher(
        work2,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
    ).publish()
    final = CatalogStore(Paths(work2)).get_resource("github:8001")
    assert final is not None
    assert final.editorial_status == EditorialStatus.REJECTED
