from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "pyproject.toml").exists() and (p / "config").exists():
            return p
        if (p / "pyproject.toml").exists() and (p / "src" / "jev_awesome").exists():
            return p
    # Fallback: package relative
    return Path(__file__).resolve().parents[2]


class Paths:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or find_repo_root()
        self.config = self.root / "config"
        self.data = self.root / "data"
        self.resources = self.data / "resources"
        self.observations = self.data / "observations"
        self.inbox = self.data / "inbox"
        self.decisions = self.data / "decisions"
        self.events = self.data / "events"
        self.cache = self.data / "cache"
        self.reports = self.data / "reports"
        self.automation = self.data / "automation"
        self.templates = self.root / "templates"
        self.docs = self.root / "docs"
        self.categories = self.docs / "categories"
        self.updates = self.docs / "updates"
        self.site_out = self.root / "site" / "dist"
        self.schemas = self.root / "schemas"

    def ensure_data_dirs(self) -> None:
        for d in (
            self.resources,
            self.observations,
            self.inbox,
            self.decisions,
            self.events,
            self.cache,
            self.reports,
            self.automation,
        ):
            d.mkdir(parents=True, exist_ok=True)
