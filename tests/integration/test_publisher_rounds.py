"""Integration: production Publisher + temp bare Git + FakeGitHubTransport."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from jev_awesome.automation.git_workspace import (
    GitWorkspace,
    clone_from_bare,
    init_bare_remote,
    run_git,
    seed_main_repo,
)
from jev_awesome.automation.github_transport import FakeGitHubTransport
from jev_awesome.automation.publisher import (
    Publisher,
    PublishOptions,
    reject_malicious_artifact_paths,
)
from jev_awesome.automation.write_policy import WritePolicyError, filter_machine_resource_update
from jev_awesome.models import (
    EditorialStatus,
    JevRelationship,
    OfficialStatus,
    PrimaryCategory,
    Resource,
    ResourceKind,
    VerificationLevel,
)
from jev_awesome.normalize import content_hash
from jev_awesome.paths import Paths
from jev_awesome.store import CatalogStore

MIN_TEMPLATES = {
    "templates/README.md.j2": "{{ generated_start }}\ncurated={{ curated|length }}\n{{ generated_end }}\n",
    "templates/README.en.md.j2": "{{ generated_start }}\nen={{ curated|length }}\n{{ generated_end }}\n",
    "templates/category.md.j2": "{{ generated_start }}\n{{ meta.slug }}:{{ items|length }}\n{{ generated_end }}\n",
    "config/sources.yaml": "sources: {}\n",
    "config/policy.yaml": "{}\n",
    "config/runtime.yaml": "classifier_mode: rules\nauto_pr_enabled: false\n",
    "pyproject.toml": "[project]\nname='jev-awesome'\nversion='0.1.0'\n",
}


def _resource(rid: str, title: str, discovered: str) -> Resource:
    return Resource(
        id=rid,
        resource_kind=ResourceKind.APPLICATION,
        primary_category=PrimaryCategory.APPLICATIONS,
        canonical_url=f"https://github.com/example/{title}",
        original_title=title,
        first_discovered_at=datetime.fromisoformat(discovered.replace("Z", "+00:00")),
        editorial_status=EditorialStatus.PENDING,
        verification_level=VerificationLevel.DISCOVERED,
        official_status=OfficialStatus.UNKNOWN,
        jev_relationship=JevRelationship.UNCLEAR,
        content_hash=content_hash(title),
        github_full_name=f"example/{title}",
    )


def _setup_repo(tmp_path: Path) -> tuple[Path, Path, GitWorkspace, FakeGitHubTransport]:
    bare = init_bare_remote(tmp_path / "remote.git")
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    files = dict(MIN_TEMPLATES)
    files["README.md"] = (
        "<!-- JEV-AWESOME:GENERATED-START -->\ncurated=0\n<!-- JEV-AWESOME:GENERATED-END -->\n"
    )
    files["README.en.md"] = files["README.md"]
    for cat in (
        "official",
        "getting-started",
        "applications",
        "sdk-integrations",
        "evals-limits",
        "research-alts",
    ):
        files[f"docs/categories/{cat}.md"] = f"# {cat}\n"
    files["data/inbox/.gitkeep"] = ""
    files["data/resources/.gitkeep"] = ""
    files["data/events/.gitkeep"] = ""
    files["data/decisions/.gitkeep"] = ""
    seed_main_repo(seed_dir, files)
    run_git(seed_dir, "remote", "add", "origin", str(bare))
    run_git(seed_dir, "push", "-u", "origin", "main")

    work = tmp_path / "work"
    ws = clone_from_bare(bare, work)
    # Ensure templates survive clone (bare round-trip)
    for rel, content in MIN_TEMPLATES.items():
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(content, encoding="utf-8")
    # rename remote for publisher isolation naming
    run_git(work, "remote", "rename", "origin", "publish-remote")
    transport = FakeGitHubTransport()
    return bare, work, ws, transport


def _inbox_ids(root: Path) -> set[str]:
    store = CatalogStore(Paths(root))
    return {r.id for r in store.list_resources(status_dir="inbox")}


def _write_candidate(root: Path, resource: Resource) -> None:
    CatalogStore(Paths(root)).save_resource(resource, inbox=True)


def test_t19_three_rounds_unmerged_retain_candidates(tmp_path: Path):
    bare, work, ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(
        enabled=True,
        dry_run=False,
        remote_name="publish-remote",
        pause_on_manual=True,
    )

    # Round 1: A
    _write_candidate(work, _resource("github:1001", "proj-a", "2026-09-01T00:00:00+00:00"))
    pub = Publisher(work, transport=transport, opts=opts)
    r1 = pub.publish()
    assert r1.status == "success" and r1.reason == "pr_created"
    assert r1.pr_number == 1
    assert len(transport.open_robot_prs(opts.robot_branch)) == 1

    # Simulate next runner: clone fresh main, merge robot branch data
    work2 = tmp_path / "work2"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work2")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=work2, known_robot_shas=set(pub.git.known_robot_shas or [])).ensure_identity()
    run_git(work2, "fetch", "publish-remote")
    robot_tree = tmp_path / "robot1"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot1")
    CatalogStore(Paths(work2)).merge_catalog_from_branch_files(robot_tree)

    # Round 2: only B (A must remain from merge)
    assert "github:1001" in _inbox_ids(work2)
    a_before = CatalogStore(Paths(work2)).get_resource("github:1001")
    assert a_before is not None
    first_a = a_before.first_discovered_at
    _write_candidate(work2, _resource("github:1002", "proj-b", "2026-09-02T00:00:00+00:00"))
    opts2 = PublishOptions(
        enabled=True,
        dry_run=False,
        remote_name="publish-remote",
        last_robot_sha=r1.commit_sha,
    )
    pub2 = Publisher(work2, transport=transport, opts=opts2)
    pub2.git.known_robot_shas = set(pub.git.known_robot_shas or [])
    r2 = pub2.publish()
    assert r2.status == "success"
    assert r2.reason == "pr_updated"
    assert r2.pr_number == 1  # same PR
    assert len(transport.open_robot_prs(opts.robot_branch)) == 1

    robot2 = tmp_path / "robot2"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot2")
    ids2 = _inbox_ids(robot2)
    assert ids2 >= {"github:1001", "github:1002"}
    a_after = CatalogStore(Paths(robot2)).get_resource("github:1001")
    assert a_after is not None
    assert a_after.first_discovered_at == first_a

    # Round 3: C
    work3 = tmp_path / "work3"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work3")
    run_git(work3, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(
        root=work3, known_robot_shas=set(pub2.git.known_robot_shas or [])
    ).ensure_identity()
    run_git(work3, "fetch", "publish-remote")
    CatalogStore(Paths(work3)).merge_catalog_from_branch_files(robot2)
    _write_candidate(work3, _resource("github:1003", "proj-c", "2026-09-03T00:00:00+00:00"))
    opts3 = PublishOptions(
        enabled=True,
        dry_run=False,
        remote_name="publish-remote",
        last_robot_sha=r2.commit_sha,
    )
    pub3 = Publisher(work3, transport=transport, opts=opts3)
    pub3.git.known_robot_shas = set(pub2.git.known_robot_shas or [])
    r3 = pub3.publish()
    assert r3.status == "success"
    assert len(transport.open_robot_prs(opts.robot_branch)) == 1

    robot3 = tmp_path / "robot3"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot3")
    assert _inbox_ids(robot3) >= {"github:1001", "github:1002", "github:1003"}

    # Round 4: no change → no_diff / no new transport write beyond GET
    work4 = tmp_path / "work4"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work4")
    run_git(work4, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(
        root=work4, known_robot_shas=set(pub3.git.known_robot_shas or [])
    ).ensure_identity()
    CatalogStore(Paths(work4)).merge_catalog_from_branch_files(robot3)
    calls_before = len(transport.calls)
    opts4 = PublishOptions(
        enabled=True,
        dry_run=False,
        remote_name="publish-remote",
        last_robot_sha=r3.commit_sha,
    )
    pub4 = Publisher(work4, transport=transport, opts=opts4)
    pub4.git.known_robot_shas = set(pub3.git.known_robot_shas or [])
    r4 = pub4.publish()
    assert r4.status in {"no_diff", "success"}
    if r4.status == "no_diff":
        # no push implied — allow GETs only after
        write_calls = [c for c in transport.calls[calls_before:] if c.method in {"POST", "PATCH"}]
        assert write_calls == []


def test_t20_manual_remote_divergence_pauses(tmp_path: Path):
    bare, work, ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:2001", "m1", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "success"

    # Divergent remote sha not in known robot set
    work2 = tmp_path / "work_m"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work_m")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=work2, known_robot_shas=set()).ensure_identity()
    opts2 = PublishOptions(
        enabled=True,
        dry_run=False,
        remote_name="publish-remote",
        last_robot_sha=r1.commit_sha,
        pause_on_manual=True,
    )
    # Pretend remote advanced to unknown sha
    transport.set_branch_sha(opts.robot_branch, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
    # Also update ls-remote by pushing a human commit on robot branch
    human = tmp_path / "human"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "human")
    GitWorkspace(root=human, known_robot_shas=set()).ensure_identity()
    (human / "SECRET_NOTE.md").write_text("human edit\n", encoding="utf-8")
    run_git(human, "add", "SECRET_NOTE.md")
    run_git(human, "commit", "-m", "human edit on robot branch")
    run_git(human, "push", "origin", opts.robot_branch)
    human_sha = run_git(human, "rev-parse", "HEAD").stdout.strip()
    transport.set_branch_sha(opts.robot_branch, human_sha)

    _write_candidate(work2, _resource("github:2002", "m2", "2026-09-02T00:00:00+00:00"))
    # merge previous robot without human file
    robot = tmp_path / "robot_m"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot_m")
    CatalogStore(Paths(work2)).merge_catalog_from_branch_files(robot)

    pub = Publisher(work2, transport=transport, opts=opts2)
    # known set only has r1 — human_sha unknown
    pub.git.known_robot_shas = {r1.commit_sha} if r1.commit_sha else set()
    result = pub.publish()
    assert result.status == "paused"
    assert (work2 / "data" / "reports" / "pending-robot-write.json").exists()


def test_t22_disabled_and_dry_run_no_writes(tmp_path: Path):
    bare, work, ws, transport = _setup_repo(tmp_path)
    _write_candidate(work, _resource("github:3001", "d1", "2026-09-01T00:00:00+00:00"))
    r = Publisher(
        work,
        transport=transport,
        opts=PublishOptions(enabled=False, dry_run=False, remote_name="publish-remote"),
    ).publish()
    assert r.status == "skipped" and r.reason == "disabled_by_configuration"
    assert transport.calls == []

    r2 = Publisher(
        work,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=True, remote_name="publish-remote"),
    ).publish()
    assert r2.status == "skipped" and r2.reason == "dry_run"
    assert transport.calls == []


def test_t30_malicious_artifact_paths_rejected():
    with pytest.raises(WritePolicyError):
        reject_malicious_artifact_paths(["../etc/passwd"])
    with pytest.raises(WritePolicyError):
        reject_malicious_artifact_paths(["src/jev_awesome/cli.py"])
    with pytest.raises(WritePolicyError):
        reject_malicious_artifact_paths([".github/workflows/ci.yml"])
    reject_malicious_artifact_paths(["data/inbox/github_1.json"])


def test_t09_field_policy_preserves_editorial(tmp_path: Path):
    existing = {
        "id": "github:1",
        "summary_zh": "人工摘要",
        "jev_role": "角色",
        "editorial_status": "proposed",
        "first_discovered_at": "2026-01-01T00:00:00+00:00",
        "review_record": {"reviewer": "alice", "decision": None},
        "verification_level": "source_checked",
        "evidence": [
            {
                "url": "https://example.com",
                "source_type": "x",
                "checked_at": "2026-01-01T00:00:00+00:00",
                "supports": "y",
            }
        ],
    }
    incoming = {
        **existing,
        "summary_zh": "机器覆盖",
        "jev_role": "坏",
        "editorial_status": "curated",
        "content_hash": "abc",
    }
    with pytest.raises(WritePolicyError):
        filter_machine_resource_update(existing, incoming)

    incoming2 = {
        **existing,
        "summary_zh": "机器覆盖",
        "content_hash": "abc",
        "editorial_status": "proposed",
    }
    out = filter_machine_resource_update(existing, incoming2)
    assert out["summary_zh"] == "人工摘要"
    assert out["content_hash"] == "abc"


def test_t21_closed_unmerged_pr_does_not_auto_reopen(tmp_path: Path):
    bare, work, _ws, transport = _setup_repo(tmp_path)
    opts = PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote")
    _write_candidate(work, _resource("github:4001", "c1", "2026-09-01T00:00:00+00:00"))
    r1 = Publisher(work, transport=transport, opts=opts).publish()
    assert r1.status == "success" and r1.pr_number == 1

    transport.close_pr(1, merged=False)

    work2 = tmp_path / "work_c"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "work_c")
    run_git(work2, "remote", "rename", "origin", "publish-remote")
    known = {r1.commit_sha} if r1.commit_sha else set()
    GitWorkspace(root=work2, known_robot_shas=known).ensure_identity()
    robot = tmp_path / "robot_c"
    run_git(tmp_path, "clone", "-b", opts.robot_branch, str(bare), "robot_c")
    CatalogStore(Paths(work2)).merge_catalog_from_branch_files(robot)
    _write_candidate(work2, _resource("github:4002", "c2", "2026-09-02T00:00:00+00:00"))

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
    assert result.status == "paused"
    assert result.reason == "previous_pr_closed_unmerged"
    assert len(transport.open_robot_prs(opts.robot_branch)) == 0
