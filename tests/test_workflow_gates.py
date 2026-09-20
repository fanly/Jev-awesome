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
    assert "payload_ready == 'true'" in cond
    assert "refs/heads/main" in cond
    assert "workflow_dispatch" in cond
    assert "schedule" in cond
    # Whitelist overall — never exclusion-style != failed / != skipped
    assert "overall == 'success'" in cond
    assert "overall == 'degraded'" in cond
    assert "!= 'failed'" not in cond
    assert "!= 'skipped'" not in cond


def test_workflow_publish_passes_trusted_identity_env():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "EXPECTED_SOURCE_SHA" in text
    assert "EXPECTED_RUN_ID" in text
    assert "EXPECTED_PRODUCER_ATTEMPT" in text
    assert "ACTUAL_CHECKOUT_SHA" in text
    assert "needs.collect.outputs.source_sha" in text
    data = _load()
    checkout = data["jobs"]["publish-pr"]["steps"][0]
    assert checkout["with"]["ref"] == "${{ needs.collect.outputs.source_sha }}"


def test_workflow_forces_ci_no_fake_ip():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert 'JEV_ALLOW_FAKE_IP: "0"' in text
    assert 'CI: "true"' in text
