"""Executable checks on collect.yml gate semantics (not a truth-table-only doc)."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "collect.yml"


def _load() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_publish_not_placeholder():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "publish-pr" in text
    assert "jev-awesome publish" in text
    assert "exit 0" not in text.split("publish-pr", 1)[1][:800]
    assert 'echo "publish skipped' not in text


def test_workflow_permissions_scoped():
    data = _load()
    assert data["permissions"] == {"contents": "read"}
    collect = data["jobs"]["collect"]
    assert collect["permissions"] == {"contents": "read"}
    publish = data["jobs"]["publish-pr"]
    assert publish["permissions"]["contents"] == "write"
    assert publish["permissions"]["pull-requests"] == "write"
    assert "pages" not in publish["permissions"]


def test_workflow_publish_requires_auto_pr_and_not_dry_run():
    data = _load()
    cond = data["jobs"]["publish-pr"]["if"]
    assert "dry_run == 'false'" in cond
    assert "auto_pr == 'true'" in cond
    assert "fanly/Jev-awesome" in cond


def test_workflow_forces_ci_no_fake_ip():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'JEV_ALLOW_FAKE_IP: "0"' in text
    assert 'CI: "true"' in text
