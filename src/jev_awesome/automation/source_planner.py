"""Per-source collection cadence planner.

Caller responsibilities (documented by design):
- ``dry_run`` must NOT advance durable checkpoints — this module never writes them.
- Source failure must NOT advance checkpoints — only the caller may persist success.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.dates import utc_now

_FREQ_RE = re.compile(r"^(\d+)([hdw])$", re.I)


class PlanStatus(StrEnum):
    DUE = "due"
    NOT_DUE = "not_due"
    FORCED = "forced"
    BACKFILL = "backfill"


@dataclass(frozen=True)
class PlanDecision:
    status: PlanStatus
    frequency: str | None
    interval: timedelta | None
    last_successful_at: datetime | None
    next_due_at: datetime | None
    reason: str

    @property
    def should_run(self) -> bool:
        return self.status != PlanStatus.NOT_DUE


def parse_frequency(frequency: str) -> timedelta:
    """Parse ``Nh`` / ``Nd`` / ``Nw`` frequency strings."""
    raw = (frequency or "").strip()
    m = _FREQ_RE.match(raw)
    if not m:
        raise ValueError(f"invalid frequency: {frequency!r} (expected Nh/Nd/Nw)")
    n = int(m.group(1))
    if n < 1:
        raise ValueError(f"frequency count must be >= 1: {frequency!r}")
    unit = m.group(2).lower()
    if unit == "h":
        return timedelta(hours=n)
    if unit == "d":
        return timedelta(days=n)
    return timedelta(weeks=n)


def plan_source(
    *,
    now: datetime,
    frequency: str | None,
    last_successful_at: datetime | None = None,
    mode: str = "incremental",
    force: bool = False,
    dry_run: bool = False,
) -> PlanDecision:
    """Decide whether a source should collect this round.

    Modes ``all`` / ``refresh`` always run. ``force`` yields ``forced``.
    Missing ``last_successful_at`` yields ``backfill``.
    ``dry_run`` only affects the reason string — this function never persists state.
    """
    _ = dry_run  # caller must not advance checkpoints on dry_run
    mode_l = (mode or "incremental").lower()

    if force:
        interval = parse_frequency(frequency) if frequency else None
        return PlanDecision(
            status=PlanStatus.FORCED,
            frequency=frequency,
            interval=interval,
            last_successful_at=last_successful_at,
            next_due_at=now,
            reason="force=True",
        )

    if mode_l in {"all", "refresh"}:
        interval = parse_frequency(frequency) if frequency else None
        return PlanDecision(
            status=PlanStatus.DUE,
            frequency=frequency,
            interval=interval,
            last_successful_at=last_successful_at,
            next_due_at=now,
            reason=f"mode={mode_l}",
        )

    if not frequency:
        return PlanDecision(
            status=PlanStatus.DUE,
            frequency=None,
            interval=None,
            last_successful_at=last_successful_at,
            next_due_at=now,
            reason="no_frequency_configured",
        )

    interval = parse_frequency(frequency)
    if last_successful_at is None:
        return PlanDecision(
            status=PlanStatus.BACKFILL,
            frequency=frequency,
            interval=interval,
            last_successful_at=None,
            next_due_at=now,
            reason="no_prior_success",
        )

    last = last_successful_at
    if last.tzinfo is None and now.tzinfo is not None:
        last = last.replace(tzinfo=now.tzinfo)
    elif now.tzinfo is None and last.tzinfo is not None:
        now = now.replace(tzinfo=last.tzinfo)

    next_due = last + interval
    if now >= next_due:
        return PlanDecision(
            status=PlanStatus.DUE,
            frequency=frequency,
            interval=interval,
            last_successful_at=last_successful_at,
            next_due_at=next_due,
            reason="interval_elapsed",
        )
    return PlanDecision(
        status=PlanStatus.NOT_DUE,
        frequency=frequency,
        interval=interval,
        last_successful_at=last_successful_at,
        next_due_at=next_due,
        reason="within_interval",
    )


class SourceCheckpointStore:
    """Durable per-source last-success timestamps.

    Path default: ``data/automation/source_checkpoints.json``.
    Only write on successful non-dry-run source completion (caller-enforced).
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        sources = data.get("sources") if "sources" in data else data
        return sources if isinstance(sources, dict) else {}

    def last_successful_at(self, source_id: str) -> datetime | None:
        entry = self.load().get(source_id) or {}
        raw = entry.get("last_successful_at")
        if not raw:
            return None
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))

    def record_success(
        self,
        source_id: str,
        *,
        at: datetime | None = None,
        coverage_status: str | None = None,
        dry_run: bool = False,
        meta: dict | None = None,
    ) -> Path | None:
        """Persist success. Returns None when dry_run (no advance)."""
        if dry_run:
            return None
        when = at or utc_now()
        all_entries = self.load()
        entry = dict(all_entries.get(source_id) or {})
        entry["last_successful_at"] = when.isoformat()
        if coverage_status is not None:
            entry["coverage_status"] = coverage_status
        if meta:
            entry["meta"] = {**(entry.get("meta") or {}), **meta}
        all_entries[source_id] = entry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "1",
            "updated_at": utc_now().isoformat(),
            "sources": all_entries,
        }
        atomic_write_text(self.path, json.dumps(payload, indent=2) + "\n")
        return self.path
