"""F1: catalog payload handoff across independent collect/publish checkouts."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jev_awesome.automation.git_workspace import GitWorkspace, run_git
from jev_awesome.automation.payload import (
    PayloadError,
    export_catalog_payload,
    import_catalog_payload,
)
from jev_awesome.automation.publisher import Publisher, PublishOptions
from tests.integration.test_publisher_rounds import (
    _inbox_ids,
    _resource,
    _setup_repo,
    _write_candidate,
)


def test_payload_handoff_two_independent_checkouts(tmp_path: Path) -> None:
    """job_collect exports A; job_publish on fresh main imports payload only — A appears."""
    bare, collect_work, _ws, transport = _setup_repo(tmp_path / "shared")

    # --- job_collect checkout ---
    _write_candidate(
        collect_work, _resource("github:8101", "payload-a", "2026-09-01T00:00:00+00:00")
    )
    payload_dir = tmp_path / "artifacts" / "catalog-payload"
    export_catalog_payload(
        collect_work,
        out_dir=payload_dir,
        meta={
            "repository": "fanly/Jev-awesome",
            "source_sha": run_git(collect_work, "rev-parse", "HEAD").stdout.strip(),
            "run_id": "test-run",
            "attempt": 1,
        },
    )
    assert (payload_dir / "manifest.json").is_file()
    assert any((payload_dir / "resources").glob("*.json"))

    # Destroy collect workdir — publish must not see it
    shutil.rmtree(collect_work)
    assert not collect_work.exists()

    # --- job_publish: fresh main clone (cannot see collect dir) ---
    publish_work = tmp_path / "job_publish"
    run_git(tmp_path, "clone", "-b", "main", str(bare), "job_publish")
    run_git(publish_work, "remote", "rename", "origin", "publish-remote")
    GitWorkspace(root=publish_work, known_robot_shas=set()).ensure_identity()

    assert "github:8101" not in _inbox_ids(publish_work)

    imported = import_catalog_payload(
        payload_dir,
        publish_work,
        expected_repo="fanly/Jev-awesome",
        require_trusted_identity=False,
    )
    assert imported.imported == 1
    assert "github:8101" in imported.resource_ids
    assert "github:8101" in _inbox_ids(publish_work)

    result = Publisher(
        publish_work,
        transport=transport,
        opts=PublishOptions(enabled=True, dry_run=False, remote_name="publish-remote"),
    ).publish()
    assert result.status == "success"
    assert result.pr_number == 1

    robot = tmp_path / "robot-payload"
    run_git(tmp_path, "clone", "-b", "automation/catalog-update", str(bare), "robot-payload")
    assert "github:8101" in _inbox_ids(robot)


def test_publish_without_payload_fails_when_required(tmp_path: Path) -> None:
    """Missing payload must not look like no_diff success."""
    bare, work, _ws, transport = _setup_repo(tmp_path)
    missing = tmp_path / "no-such-payload"
    with pytest.raises(PayloadError, match="missing"):
        import_catalog_payload(
            missing,
            work,
            expected_repo="fanly/Jev-awesome",
            require_trusted_identity=False,
        )

    # CLI-style: missing path checked before publish
    assert not missing.exists()
