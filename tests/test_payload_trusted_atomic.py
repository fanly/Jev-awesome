"""G1/G2: payload trusted identity + dry-run zero side effects + atomic import."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from jev_awesome.automation.payload import (
    PayloadError,
    export_catalog_payload,
    import_catalog_payload,
)
from jev_awesome.cli import main
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


def _make(rid: str, **kwargs) -> Resource:
    base = dict(
        id=rid,
        resource_kind=ResourceKind.APPLICATION,
        primary_category=PrimaryCategory.APPLICATIONS,
        canonical_url=f"https://github.com/example/{rid}",
        original_title=rid,
        first_discovered_at=datetime(2026, 9, 1, tzinfo=UTC),
        editorial_status=EditorialStatus.PENDING,
        verification_level=VerificationLevel.DISCOVERED,
        official_status=OfficialStatus.UNKNOWN,
        jev_relationship=JevRelationship.UNCLEAR,
        content_hash=content_hash(rid),
    )
    base.update(kwargs)
    return Resource.model_validate(base)


def _export_two(tmp_path: Path) -> tuple[Path, Path]:
    collect = tmp_path / "collect"
    Paths(collect).ensure_data_dirs()
    store = CatalogStore(Paths(collect))
    store.save_resource(_make("github:g1a"), inbox=True)
    store.save_resource(_make("github:g1b"), inbox=True)
    payload_dir = tmp_path / "payload"
    export_catalog_payload(
        collect,
        out_dir=payload_dir,
        meta={
            "repository": "fanly/Jev-awesome",
            "source_sha": "abcdef1234567",
            "run_id": "99",
            "attempt": 1,
        },
    )
    return collect, payload_dir


def test_payload_requires_trusted_identity_in_production(tmp_path: Path) -> None:
    _, payload_dir = _export_two(tmp_path)
    trusted = tmp_path / "trusted"
    Paths(trusted).ensure_data_dirs()
    with pytest.raises(PayloadError, match="expected_source_sha"):
        import_catalog_payload(
            payload_dir,
            trusted,
            expected_repo="fanly/Jev-awesome",
            require_trusted_identity=True,
        )


def test_payload_trusted_identity_mismatch_before_write(tmp_path: Path) -> None:
    _, payload_dir = _export_two(tmp_path)
    trusted = tmp_path / "trusted"
    Paths(trusted).ensure_data_dirs()
    with pytest.raises(PayloadError, match="run_id mismatch"):
        import_catalog_payload(
            payload_dir,
            trusted,
            expected_repo="fanly/Jev-awesome",
            expected_source_sha="abcdef1234567",
            expected_run_id="other-run",
            expected_producer_attempt=1,
            actual_checkout_sha="abcdef1234567",
            require_trusted_identity=True,
        )
    assert list((trusted / "data" / "inbox").glob("*.json")) == []


def test_payload_checkout_sha_must_match_expected(tmp_path: Path) -> None:
    _, payload_dir = _export_two(tmp_path)
    trusted = tmp_path / "trusted"
    Paths(trusted).ensure_data_dirs()
    with pytest.raises(PayloadError, match="actual_checkout_sha"):
        import_catalog_payload(
            payload_dir,
            trusted,
            expected_repo="fanly/Jev-awesome",
            expected_source_sha="abcdef1234567",
            expected_run_id="99",
            expected_producer_attempt=1,
            actual_checkout_sha="deadbeef12345",
            require_trusted_identity=True,
        )


def test_payload_mid_validation_failure_zero_writes(tmp_path: Path) -> None:
    """Second resource fails validation → first must not be written either."""
    _, payload_dir = _export_two(tmp_path)
    trusted = tmp_path / "trusted"
    Paths(trusted).ensure_data_dirs()

    # Corrupt the second resource JSON so model_validate fails after first stages
    files = sorted((payload_dir / "resources").glob("*.json"))
    assert len(files) == 2
    bad = files[-1]
    bad.write_text("{not-json", encoding="utf-8")
    # Fix manifest hash for the corrupted file so we reach resource validation
    from jev_awesome.automation.payload import _sha256_file

    manifest = json.loads((payload_dir / "manifest.json").read_text(encoding="utf-8"))
    rel = f"resources/{bad.name}"
    manifest["file_hashes"][rel] = _sha256_file(bad)
    check = {k: v for k, v in manifest.items() if k != "payload_hash"}
    canonical = json.dumps(check, sort_keys=True, separators=(",", ":")).encode()
    manifest["payload_hash"] = hashlib.sha256(canonical).hexdigest()
    (payload_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    with pytest.raises(PayloadError, match="corrupt resource"):
        import_catalog_payload(
            payload_dir,
            trusted,
            expected_repo="fanly/Jev-awesome",
            require_trusted_identity=False,
        )
    assert list((trusted / "data" / "inbox").glob("*.json")) == []


def test_publish_dry_run_with_payload_does_not_write_inbox(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G2: --dry-run/--disabled returns before payload import."""
    _, payload_dir = _export_two(tmp_path)
    work = tmp_path / "work"
    Paths(work).ensure_data_dirs()
    (work / "pyproject.toml").write_text("[project]\nname='jev-awesome'\n", encoding="utf-8")
    monkeypatch.setattr("jev_awesome.cli._paths", lambda: Paths(work))

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["publish", "--disabled", "--payload", str(payload_dir)],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "disabled" in result.output or "skipped" in result.output
    assert list((work / "data" / "inbox").glob("*.json")) == []

    result2 = runner.invoke(
        main,
        ["publish", "--enabled", "--dry-run", "--payload", str(payload_dir)],
        catch_exceptions=False,
    )
    assert result2.exit_code == 0
    assert list((work / "data" / "inbox").glob("*.json")) == []
