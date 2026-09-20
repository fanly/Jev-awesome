"""Light weekly digest wrapper (writes docs/updates/YYYY-Www.md)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jev_awesome.paths import Paths
from jev_awesome.rendering.weekly import build_weekly, write_weekly
from jev_awesome.store import CatalogStore

__all__ = ["build_weekly", "write_weekly", "write_weekly_if_material"]


def write_weekly_if_material(
    store: CatalogStore | None = None,
    paths: Paths | None = None,
    *,
    tz_name: str = "Asia/Shanghai",
    now: datetime | None = None,
) -> Path | None:
    """Write ``docs/updates/YYYY-Www.md`` only when material content exists."""
    return write_weekly(store, paths, tz_name=tz_name, now=now)
