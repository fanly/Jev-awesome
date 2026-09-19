from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.models import (
    CatalogEvent,
    Decision,
    Observation,
    Resource,
    RunReport,
)
from jev_awesome.paths import Paths

T = TypeVar("T", bound=BaseModel)

EDITORIAL_FIELDS = frozenset(
    {
        "summary_zh",
        "summary_en",
        "developer_value",
        "jev_role",
        "prerequisites",
        "limitations",
        "editorial_status",
        "verification_level",
        "evidence",
        "review_record",
        "primary_category",
        "resource_kind",
        "jev_relationship",
        "official_status",
        "license_status",
        "license_identifier",
        "license_evidence",
        "original_title",
    }
)


def _dump_json(model: BaseModel) -> str:
    return model.model_dump_json(indent=2) + "\n"


def _load_json(path: Path, model: type[T]) -> T:
    data = json.loads(path.read_text(encoding="utf-8"))
    return model.model_validate(data)


class CatalogStore:
    def __init__(self, paths: Paths | None = None) -> None:
        self.paths = paths or Paths()
        self.paths.ensure_data_dirs()

    def resource_path(self, resource_id: str, *, inbox: bool = False) -> Path:
        safe = resource_id.replace(":", "_").replace("/", "_")
        base = self.paths.inbox if inbox else self.paths.resources
        return base / f"{safe}.json"

    def list_resources(self, *, status_dir: str = "resources") -> list[Resource]:
        directory = {
            "resources": self.paths.resources,
            "inbox": self.paths.inbox,
        }[status_dir]
        items: list[Resource] = []
        if not directory.exists():
            return items
        for path in sorted(directory.glob("*.json")):
            items.append(_load_json(path, Resource))
        return items

    def get_resource(self, resource_id: str) -> Resource | None:
        for inbox in (False, True):
            path = self.resource_path(resource_id, inbox=inbox)
            if path.exists():
                return _load_json(path, Resource)
        return None

    def save_resource(self, resource: Resource, *, inbox: bool | None = None) -> Path:
        if inbox is None:
            inbox = resource.editorial_status.value in {"pending", "proposed"} and not (
                self.resource_path(resource.id, inbox=False).exists()
                and resource.editorial_status.value in {"curated", "archived", "rejected"}
            )
            if resource.editorial_status.value in {"curated", "archived", "rejected"}:
                inbox = False
            elif resource.editorial_status.value in {"pending", "proposed"}:
                # curated lives in resources; pending/proposed in inbox unless already curated path
                curated_path = self.resource_path(resource.id, inbox=False)
                if curated_path.exists():
                    existing = _load_json(curated_path, Resource)
                    if existing.editorial_status.value in {"curated", "archived"}:
                        inbox = False
                    else:
                        inbox = True
                else:
                    inbox = True
        path = self.resource_path(resource.id, inbox=inbox)
        # Remove from the other location to avoid dual state
        other = self.resource_path(resource.id, inbox=not inbox)
        atomic_write_text(path, _dump_json(resource))
        if other.exists() and other != path:
            other.unlink()
        return path

    def save_observation(self, obs: Observation) -> Path:
        safe = obs.resource_id.replace(":", "_").replace("/", "_")
        path = self.paths.observations / f"{safe}.json"
        atomic_write_text(path, _dump_json(obs))
        return path

    def save_decision(self, decision: Decision) -> Path:
        safe = decision.resource_id.replace(":", "_").replace("/", "_")
        path = self.paths.decisions / f"{safe}.json"
        atomic_write_text(path, _dump_json(decision))
        return path

    def get_decision(self, resource_id: str) -> Decision | None:
        safe = resource_id.replace(":", "_").replace("/", "_")
        path = self.paths.decisions / f"{safe}.json"
        if not path.exists():
            return None
        return _load_json(path, Decision)

    def save_event(self, event: CatalogEvent) -> Path:
        path = self.paths.events / f"{event.id}.json"
        atomic_write_text(path, _dump_json(event))
        return path

    def list_events(self) -> list[CatalogEvent]:
        items: list[CatalogEvent] = []
        for path in sorted(self.paths.events.glob("*.json")):
            items.append(_load_json(path, CatalogEvent))
        return items

    def save_report(self, report: RunReport) -> Path:
        path = self.paths.reports / f"{report.run_id}.json"
        atomic_write_text(path, _dump_json(report))
        return path

    def all_known(self) -> list[Resource]:
        by_id: dict[str, Resource] = {}
        for r in self.list_resources(status_dir="resources"):
            by_id[r.id] = r
        for r in self.list_resources(status_dir="inbox"):
            by_id.setdefault(r.id, r)
        return list(by_id.values())

    def counts(self) -> dict[str, int]:
        curated = proposed = pending = rejected = archived = 0
        for r in self.all_known():
            s = r.editorial_status.value
            if s == "curated":
                curated += 1
            elif s == "proposed":
                proposed += 1
            elif s == "pending":
                pending += 1
            elif s == "rejected":
                rejected += 1
            elif s == "archived":
                archived += 1
        return {
            "curated": curated,
            "proposed": proposed,
            "pending": pending,
            "rejected": rejected,
            "archived": archived,
            "inbox": pending + proposed,
            "total": curated + proposed + pending + rejected + archived,
        }

    def merge_catalog_from_branch_files(self, other_root: Path) -> int:
        """Merge inbox/resources/decisions/events from another checkout (unmerged PR)."""
        other = Paths(other_root)
        merged = 0
        for directory, loader, saver in (
            (
                other.inbox,
                lambda p: _load_json(p, Resource),
                lambda obj: self.save_resource(obj, inbox=True),
            ),
            (
                other.resources,
                lambda p: _load_json(p, Resource),
                lambda obj: self.save_resource(obj, inbox=False),
            ),
        ):
            if not directory.exists():
                continue
            for path in directory.glob("*.json"):
                incoming: Resource = loader(path)
                existing = self.get_resource(incoming.id)
                if existing is None:
                    saver(incoming)
                    merged += 1
                    continue
                # Keep earliest discovery; do not overwrite editorial
                from jev_awesome.dedupe import merge_machine_fields

                combined = merge_machine_fields(existing, incoming)
                if existing.first_discovered_at <= incoming.first_discovered_at:
                    combined = combined.model_copy(
                        update={"first_discovered_at": existing.first_discovered_at}
                    )
                else:
                    combined = combined.model_copy(
                        update={"first_discovered_at": incoming.first_discovered_at}
                    )
                # Prefer stronger editorial status
                rank = {
                    "pending": 0,
                    "proposed": 1,
                    "rejected": 2,
                    "archived": 3,
                    "curated": 4,
                }
                if rank.get(existing.editorial_status.value, 0) >= rank.get(
                    incoming.editorial_status.value, 0
                ):
                    combined = combined.model_copy(
                        update={
                            "editorial_status": existing.editorial_status,
                            "summary_zh": existing.summary_zh or incoming.summary_zh,
                            "summary_en": existing.summary_en or incoming.summary_en,
                            "developer_value": existing.developer_value or incoming.developer_value,
                            "jev_role": existing.jev_role or incoming.jev_role,
                            "limitations": existing.limitations or incoming.limitations,
                            "verification_level": existing.verification_level,
                            "evidence": existing.evidence or incoming.evidence,
                            "review_record": existing.review_record,
                        }
                    )
                self.save_resource(
                    combined,
                    inbox=combined.editorial_status.value in {"pending", "proposed"},
                )
                merged += 1
        for path in sorted(other.decisions.glob("*.json") if other.decisions.exists() else []):
            dec = _load_json(path, Decision)
            if self.get_decision(dec.resource_id) is None:
                self.save_decision(dec)
                merged += 1
        for path in sorted(other.events.glob("*.json") if other.events.exists() else []):
            dest = self.paths.events / path.name
            if not dest.exists():
                # Validate then copy
                _load_json(path, CatalogEvent)
                atomic_write_text(dest, path.read_text(encoding="utf-8"))
                merged += 1
        return merged


def export_json_schema(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, model in (
        ("resource", Resource),
        ("observation", Observation),
        ("decision", Decision),
        ("event", CatalogEvent),
        ("run_report", RunReport),
    ):
        schema = TypeAdapter(model).json_schema()
        atomic_write_text(
            out_dir / f"{name}.schema.json",
            json.dumps(schema, indent=2, ensure_ascii=False) + "\n",
        )


def load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data
