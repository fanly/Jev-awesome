"""Catalog payload handoff between collect and publish jobs.

Collect exports an allowlisted snapshot; publish imports into a trusted main
checkout with editorial merge BEFORE writing inbox. Never carries scripts,
workflows, config, or templates.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.automation.write_policy import (
    WritePolicyError,
    assert_not_symlink,
    filter_machine_resource_update,
    normalize_rel_path,
)
from jev_awesome.dates import utc_now
from jev_awesome.models import Resource
from jev_awesome.paths import Paths
from jev_awesome.store import CatalogStore

SCHEMA_VERSION = 1

FORBIDDEN_PAYLOAD_PREFIXES: tuple[str, ...] = (
    "src/",
    ".github/",
    "config/",
    "templates/",
    "scripts/",
    "tests/",
    "schemas/",
)

MAX_PAYLOAD_FILE_BYTES = 1_500_000
MAX_PAYLOAD_TOTAL_BYTES = 40_000_000
MAX_PAYLOAD_FILES = 5_000

MACHINE_STATUSES = frozenset({"pending", "proposed"})


class PayloadError(ValueError):
    """Corrupt, missing, or policy-violating catalog payload."""


@dataclass
class ImportResult:
    imported: int
    resource_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _safe_resource_filename(resource_id: str) -> str:
    return f"{resource_id.replace(':', '_').replace('/', '_')}.json"


def _assert_payload_rel(rel: str) -> str:
    p = normalize_rel_path(rel)
    if p in {"manifest.json"}:
        return p
    for pref in FORBIDDEN_PAYLOAD_PREFIXES:
        if p == pref.rstrip("/") or p.startswith(pref):
            raise PayloadError(f"forbidden payload path: {p}")
    if p.startswith("resources/") and p.endswith(".json"):
        return p
    if p.startswith("events/") and p.endswith(".json"):
        return p
    if p.startswith("observations/") and p.endswith(".json"):
        return p
    raise PayloadError(f"path not allowlisted in payload: {p}")


def _coverage_summary(root: Path) -> dict[str, Any]:
    report = root / "data" / "reports" / "latest.json"
    if not report.exists():
        return {}
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "overall": data.get("overall"),
        "run_id": data.get("run_id"),
        "coverage": data.get("coverage") or data.get("sources"),
    }


def export_catalog_payload(root: Path | str, *, out_dir: Path | str, meta: dict[str, Any]) -> Path:
    """Write allowlisted inbox/pending/proposed resources (+ optional events/obs) to out_dir."""
    root_p = Path(root)
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    res_dir = out / "resources"
    res_dir.mkdir(parents=True, exist_ok=True)

    store = CatalogStore(Paths(root_p))
    resource_ids: list[str] = []
    file_hashes: dict[str, str] = {}
    dispositions: dict[str, int] = {"pending": 0, "proposed": 0}

    for resource in store.list_resources(status_dir="inbox"):
        status = resource.editorial_status.value
        if status not in MACHINE_STATUSES:
            continue
        safe = _safe_resource_filename(resource.id)
        rel = f"resources/{safe}"
        _assert_payload_rel(rel)
        text = resource.model_dump_json(indent=2) + "\n"
        raw = text.encode("utf-8")
        if len(raw) > MAX_PAYLOAD_FILE_BYTES:
            raise PayloadError(f"resource too large: {resource.id}")
        (res_dir / safe).write_bytes(raw)
        file_hashes[rel] = _sha256_bytes(raw)
        resource_ids.append(resource.id)
        dispositions[status] = dispositions.get(status, 0) + 1

    # Optional machine-allowed events / observations (copy if present, filtered)
    for kind in ("events", "observations"):
        src = root_p / "data" / kind
        if not src.is_dir():
            continue
        dest = out / kind
        dest.mkdir(parents=True, exist_ok=True)
        for path in sorted(src.glob("*.json")):
            assert_not_symlink(path)
            rel = f"{kind}/{path.name}"
            _assert_payload_rel(rel)
            raw = path.read_bytes()
            if len(raw) > MAX_PAYLOAD_FILE_BYTES:
                raise PayloadError(f"file too large: {rel}")
            (dest / path.name).write_bytes(raw)
            file_hashes[rel] = _sha256_bytes(raw)

    if len(file_hashes) > MAX_PAYLOAD_FILES:
        raise PayloadError("too many payload files")
    total = sum((out / rel).stat().st_size for rel in file_hashes)
    if total > MAX_PAYLOAD_TOTAL_BYTES:
        raise PayloadError("payload total size too large")

    created_at = utc_now().isoformat()
    manifest_body = {
        "schema_version": SCHEMA_VERSION,
        "repository": meta.get("repository") or meta.get("expected_repo") or "fanly/Jev-awesome",
        "source_sha": meta.get("source_sha"),
        "run_id": meta.get("run_id"),
        "attempt": meta.get("attempt"),
        "created_at": created_at,
        "resource_ids": sorted(resource_ids),
        "file_hashes": file_hashes,
        "coverage": _coverage_summary(root_p),
        "dispositions": dispositions,
    }
    # payload_hash over canonical manifest without payload_hash itself
    canonical = json.dumps(manifest_body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_hash = _sha256_bytes(canonical)
    manifest_body["payload_hash"] = payload_hash

    atomic_write_text(
        out / "manifest.json",
        json.dumps(manifest_body, indent=2, ensure_ascii=False) + "\n",
    )
    return out


def import_catalog_payload(
    payload_dir: Path | str,
    trusted_root: Path | str,
    *,
    expected_repo: str,
    expected_source_sha: str | None = None,
) -> ImportResult:
    """Import payload into trusted_root inbox with editorial baseline merge.

    Raises PayloadError on missing/corrupt/mismatched payload — never silent no_diff.
    """
    payload = Path(payload_dir)
    trusted = Path(trusted_root)
    manifest_path = payload / "manifest.json"
    if not payload.is_dir():
        raise PayloadError(f"payload directory missing: {payload}")
    if not manifest_path.is_file():
        raise PayloadError(f"manifest.json missing in payload: {payload}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise PayloadError(f"corrupt manifest.json: {e}") from e

    if not isinstance(manifest, dict):
        raise PayloadError("manifest root must be object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise PayloadError(
            f"unsupported schema_version={manifest.get('schema_version')}; "
            f"expected {SCHEMA_VERSION}"
        )

    repo = manifest.get("repository")
    if repo != expected_repo:
        raise PayloadError(f"repository mismatch: payload={repo!r} expected={expected_repo!r}")

    if expected_source_sha is not None:
        src = manifest.get("source_sha")
        if src and src != expected_source_sha:
            # Documented merge rule: refuse when collect tip does not match publish base.
            raise PayloadError(
                f"source_sha mismatch: payload={src!r} expected={expected_source_sha!r} "
                "(collect/publish bases moved incompatibly; re-run collect)"
            )

    file_hashes = manifest.get("file_hashes")
    if not isinstance(file_hashes, dict) or not file_hashes:
        # Empty catalog is allowed only when resource_ids is explicitly empty list
        if manifest.get("resource_ids") not in ([], None) and not file_hashes:
            raise PayloadError("manifest file_hashes missing or empty")

    # Validate paths, sizes, hashes before any write
    total = 0
    for rel, expected_hash in (file_hashes or {}).items():
        safe_rel = _assert_payload_rel(str(rel))
        path = payload / safe_rel
        if not path.is_file():
            raise PayloadError(f"payload file missing: {safe_rel}")
        assert_not_symlink(path)
        size = path.stat().st_size
        if size > MAX_PAYLOAD_FILE_BYTES:
            raise PayloadError(f"file too large: {safe_rel}")
        total += size
        actual = _sha256_file(path)
        if actual != expected_hash:
            raise PayloadError(f"hash mismatch for {safe_rel}")
    if total > MAX_PAYLOAD_TOTAL_BYTES:
        raise PayloadError("payload total size too large")
    if len(file_hashes or {}) > MAX_PAYLOAD_FILES:
        raise PayloadError("too many payload files")

    # Verify payload_hash
    check = {k: v for k, v in manifest.items() if k != "payload_hash"}
    canonical = json.dumps(check, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if manifest.get("payload_hash") != _sha256_bytes(canonical):
        raise PayloadError("payload_hash mismatch")

    store = CatalogStore(Paths(trusted))
    imported_ids: list[str] = []
    notes: list[str] = []

    for rel in sorted(file_hashes or {}):
        if not str(rel).startswith("resources/"):
            continue
        path = payload / rel
        try:
            incoming = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise PayloadError(f"corrupt resource {rel}: {e}") from e
        if not isinstance(incoming, dict):
            raise PayloadError(f"resource must be object: {rel}")
        rid = incoming.get("id")
        if not rid:
            raise PayloadError(f"resource missing id: {rel}")

        # CRITICAL: load EXISTING from trusted_root BEFORE applying machine filter
        existing_model = store.get_resource(str(rid))
        existing = (
            json.loads(existing_model.model_dump_json()) if existing_model is not None else None
        )
        try:
            sanitized = filter_machine_resource_update(existing, incoming)
        except WritePolicyError as e:
            raise PayloadError(f"field policy rejected {rid}: {e}") from e

        resource = Resource.model_validate(sanitized)
        if resource.editorial_status.value not in MACHINE_STATUSES:
            notes.append(f"skip_non_machine_status:{rid}:{resource.editorial_status.value}")
            continue
        store.save_resource(resource, inbox=True)
        imported_ids.append(str(rid))

    # Copy events/observations that are new (machine-allowed types already in files)
    for kind in ("events", "observations"):
        src_dir = payload / kind
        if not src_dir.is_dir():
            continue
        dest_dir = trusted / "data" / kind
        dest_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(src_dir.glob("*.json")):
            rel = f"{kind}/{path.name}"
            if rel not in (file_hashes or {}):
                continue
            dest = dest_dir / path.name
            if not dest.exists():
                shutil.copy2(path, dest)
                notes.append(f"copied:{rel}")

    return ImportResult(
        imported=len(imported_ids),
        resource_ids=imported_ids,
        notes=notes,
        manifest=manifest,
    )
