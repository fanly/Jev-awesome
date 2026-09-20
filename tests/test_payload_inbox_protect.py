"""F5: payload import preserves editorial fields on trusted inbox baseline."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jev_awesome.automation.payload import export_catalog_payload, import_catalog_payload
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
        editorial_status=EditorialStatus.PROPOSED,
        verification_level=VerificationLevel.DISCOVERED,
        official_status=OfficialStatus.UNKNOWN,
        jev_relationship=JevRelationship.UNCLEAR,
        content_hash=content_hash(rid),
        summary_zh="人工摘要保留",
    )
    base.update(kwargs)
    return Resource.model_validate(base)


def test_payload_import_preserves_summary_zh(tmp_path: Path) -> None:
    main = tmp_path / "main"
    Paths(main).ensure_data_dirs()
    store = CatalogStore(Paths(main))
    store.save_resource(_make("github:55"), inbox=True)

    # Collect-side payload tries to overwrite summary
    collect = tmp_path / "collect"
    Paths(collect).ensure_data_dirs()
    bad = _make(
        "github:55",
        summary_zh="机器覆盖摘要",
        content_hash=content_hash("machine"),
    )
    CatalogStore(Paths(collect)).save_resource(bad, inbox=True)
    payload_dir = tmp_path / "payload"
    export_catalog_payload(
        collect,
        out_dir=payload_dir,
        meta={"repository": "fanly/Jev-awesome", "source_sha": "abc"},
    )

    # Tamper payload resource to ensure overwrite attempt
    res_file = next((payload_dir / "resources").glob("*.json"))
    data = json.loads(res_file.read_text(encoding="utf-8"))
    data["summary_zh"] = "机器覆盖摘要"
    data["content_hash"] = content_hash("machine2")
    res_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    # Fix manifest hash
    from jev_awesome.automation.payload import _sha256_file

    manifest = json.loads((payload_dir / "manifest.json").read_text(encoding="utf-8"))
    rel = f"resources/{res_file.name}"
    manifest["file_hashes"][rel] = _sha256_file(res_file)
    check = {k: v for k, v in manifest.items() if k != "payload_hash"}
    import hashlib
    import json as _json

    canonical = _json.dumps(check, sort_keys=True, separators=(",", ":")).encode()
    manifest["payload_hash"] = hashlib.sha256(canonical).hexdigest()
    (payload_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    result = import_catalog_payload(payload_dir, main, expected_repo="fanly/Jev-awesome")
    assert result.imported == 1
    after = store.get_resource("github:55")
    assert after is not None
    assert after.summary_zh == "人工摘要保留"
    assert after.content_hash == content_hash("machine2")
