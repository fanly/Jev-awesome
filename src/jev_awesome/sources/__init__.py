from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from jev_awesome.models import Resource, SourceResult


@dataclass
class CollectContext:
    dry_run: bool
    write_local: bool
    token: str | None = None
    max_pages: int = 2
    per_page: int = 30


class SourceAdapter(Protocol):
    source_id: str

    def collect(self, ctx: CollectContext) -> tuple[list[Resource], SourceResult]: ...
