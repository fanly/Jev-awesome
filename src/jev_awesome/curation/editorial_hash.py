"""Editorial field fingerprint for curated preservation checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from jev_awesome.models import Resource

# Fields automation must never mutate on curated (or protected) records.
EDITORIAL_FINGERPRINT_FIELDS: tuple[str, ...] = (
    "summary_zh",
    "developer_value",
    "jev_role",
    "limitations",
    "review_record",
    "verification_level",
    "editorial_status",
)


def editorial_fingerprint(resource: Resource | dict[str, Any]) -> str:
    """Stable 16-hex fingerprint of protected editorial fields."""
    if isinstance(resource, Resource):
        data = resource.model_dump(mode="json")
    else:
        data = dict(resource)
    subset = {k: data.get(k) for k in EDITORIAL_FINGERPRINT_FIELDS}
    blob = json.dumps(subset, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def curated_editorial_snapshot(resources_dir) -> dict[str, str]:
    """Map resource id → fingerprint for all curated JSON files under a directory."""
    from pathlib import Path

    from jev_awesome.models import EditorialStatus

    root = Path(resources_dir)
    out: dict[str, str] = {}
    for path in sorted(root.glob("*.json")):
        r = Resource.model_validate_json(path.read_text(encoding="utf-8"))
        if r.editorial_status == EditorialStatus.CURATED:
            out[r.id] = editorial_fingerprint(r)
    return out
