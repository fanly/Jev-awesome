"""Incremental collection checkpoints — advance only after durable save."""

from __future__ import annotations

import json
from pathlib import Path

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.dates import utc_now


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, source_id: str, shard: str = "default") -> Path:
        safe = f"{source_id}__{shard}".replace("/", "_").replace(":", "_")
        return self.root / f"{safe}.json"

    def load(self, source_id: str, shard: str = "default") -> dict | None:
        path = self.path_for(source_id, shard)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(
        self,
        source_id: str,
        *,
        shard: str = "default",
        cursor: str | None,
        coverage_status: str,
        durable: bool,
        dry_run: bool,
        meta: dict | None = None,
    ) -> Path | None:
        """Persist checkpoint only when durable=True and not dry_run."""
        if dry_run or not durable:
            return None
        payload = {
            "source_id": source_id,
            "shard": shard,
            "cursor": cursor,
            "coverage_status": coverage_status,
            "updated_at": utc_now().isoformat(),
            "meta": meta or {},
        }
        path = self.path_for(source_id, shard)
        atomic_write_text(path, json.dumps(payload, indent=2) + "\n")
        return path
