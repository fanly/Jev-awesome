"""F2: collect workflow flags truth table (same shell as CI)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "resolve_collect_flags.sh"


def _resolve(
    *,
    event_name: str,
    collector: str = "",
    auto_pr: str = "",
    input_dry: str = "",
) -> dict[str, str]:
    env = {
        **os.environ,
        "COLLECTOR_ENABLED": collector,
        "AUTO_PR_ENABLED": auto_pr,
        "EVENT_NAME": event_name,
        "INPUT_DRY": input_dry,
    }
    out = subprocess.check_output(["bash", str(SCRIPT)], env=env, text=True)
    result: dict[str, str] = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            result[k] = v
    return result


@pytest.mark.parametrize(
    "event_name,collector,input_dry,expect_dry,expect_skip",
    [
        # schedule + collector=true → dry_run=false
        ("schedule", "true", "", "false", "false"),
        # schedule + collector off → skip, dry_run stays true
        ("schedule", "", "", "true", "true"),
        ("schedule", "false", "", "true", "true"),
        ("schedule", "TRUE", "", "true", "true"),  # strict string true only
        # workflow_dispatch dry_run false → dry_run=false
        ("workflow_dispatch", "", "false", "false", "false"),
        ("workflow_dispatch", "true", "false", "false", "false"),
        # workflow_dispatch dry_run true / missing → dry_run=true
        ("workflow_dispatch", "", "true", "true", "false"),
        ("workflow_dispatch", "", "", "true", "false"),
        # schedule + collector true ignores INPUT_DRY
        ("schedule", "true", "true", "false", "false"),
    ],
)
def test_collect_flags_matrix(
    event_name: str,
    collector: str,
    input_dry: str,
    expect_dry: str,
    expect_skip: str,
) -> None:
    flags = _resolve(event_name=event_name, collector=collector, input_dry=input_dry)
    assert flags["dry_run"] == expect_dry
    assert flags["skip"] == expect_skip
    assert flags["collector"] == ("true" if collector == "true" else "false")


def test_workflow_uses_flags_script() -> None:
    text = (ROOT / ".github" / "workflows" / "collect.yml").read_text(encoding="utf-8")
    assert "scripts/resolve_collect_flags.sh" in text
    assert 'schedule" && "${collector}" == "true"' in (
        SCRIPT.read_text(encoding="utf-8")
    ) or 'EVENT_NAME}" == "schedule" && "${collector}" == "true"' in SCRIPT.read_text(
        encoding="utf-8"
    )
    assert "payload_ready" in text
    assert "catalog-payload" in text
    assert "--payload /tmp/catalog-payload" in text
