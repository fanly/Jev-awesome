from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from jev_awesome import __version__
from jev_awesome.automation.collect import CollectOptions, run_collect
from jev_awesome.automation.scheduler import describe_schedule
from jev_awesome.classification.typesafe_adapter import TypeSafeConfigError
from jev_awesome.config import AppConfig
from jev_awesome.curation.review import ReviewError, ReviewService
from jev_awesome.models import ClassifierMode
from jev_awesome.paths import Paths
from jev_awesome.rendering.render import Renderer
from jev_awesome.rendering.weekly import write_weekly
from jev_awesome.site.build import build_site
from jev_awesome.store import CatalogStore, export_json_schema

console = Console()


def _paths() -> Paths:
    return Paths()


@click.group()
@click.version_option(__version__, prog_name="jev-awesome")
def main() -> None:
    """Jev-awesome catalog tooling."""


@main.command()
def doctor() -> None:
    """Check interpreter, config, data dirs, and key presence (never print secrets)."""
    paths = _paths()
    config = AppConfig.load(paths.root)
    rows = [
        ("python", f"{sys.version.split()[0]}"),
        ("repo_root", str(paths.root)),
        ("config/sources.yaml", "ok" if (paths.config / "sources.yaml").exists() else "MISSING"),
        ("config/policy.yaml", "ok" if (paths.config / "policy.yaml").exists() else "MISSING"),
        ("config/runtime.yaml", "ok" if (paths.config / "runtime.yaml").exists() else "MISSING"),
        ("TYPESAFE_API_KEY", "present" if os.environ.get("TYPESAFE_API_KEY") else "absent"),
        ("GITHUB_TOKEN/GH_TOKEN", "present" if (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")) else "absent"),
        ("classifier_mode_default", config.runtime.classifier_mode),
        ("collector_enabled", str(config.runtime.collector_enabled)),
        ("auto_pr_enabled", str(config.runtime.auto_pr_enabled)),
        ("pages_enabled", str(config.runtime.pages_enabled)),
        ("schedule", "; ".join(describe_schedule(config.runtime.timezone))),
    ]
    table = Table(title="jev-awesome doctor")
    table.add_column("check")
    table.add_column("value")
    for k, v in rows:
        table.add_row(k, v)
    console.print(table)
    try:
        import typesafe_sdk
        from typesafe_sdk import constants

        console.print(
            f"typesafe-sdk {getattr(typesafe_sdk, '__version__', '?')} "
            f"API_KEY_ENV={constants.API_KEY_ENV}"
        )
    except ImportError:
        console.print("[yellow]typesafe-sdk not importable[/yellow]")


@main.command()
def validate() -> None:
    """Validate all resource JSON files against the schema model."""
    store = CatalogStore()
    errors: list[str] = []
    for label in ("resources", "inbox"):
        for path in sorted(getattr(store.paths, label).glob("*.json")):
            try:
                from jev_awesome.models import Resource

                Resource.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{path}: {e}")
    export_json_schema(store.paths.schemas)
    if errors:
        for e in errors:
            console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    counts = store.counts()
    console.print(f"validate ok · counts={counts} · schemas → {store.paths.schemas}")


@main.command()
@click.option("--mode", default="incremental", type=click.Choice(["incremental", "refresh", "maintenance", "all"]))
@click.option("--classifier", default="rules", type=click.Choice(["rules", "auto", "typesafe"]))
@click.option("--dry-run/--write-preview-only", default=True, help="Default dry-run; no catalog writes.")
@click.option("--write-local", is_flag=True, help="Write local catalog files (still no remote).")
@click.option("--max-pages", default=2, show_default=True)
@click.option("--merge-from", type=click.Path(path_type=Path), default=None, help="Merge unmerged robot branch checkout.")
def collect(
    mode: str,
    classifier: str,
    dry_run: bool,
    write_local: bool,
    max_pages: int,
    merge_from: Path | None,
) -> None:
    """Discover candidates. Never auto-curates."""
    if write_local:
        dry_run = False
    opts = CollectOptions(
        mode=mode,
        classifier=ClassifierMode(classifier),
        dry_run=dry_run,
        write_local=write_local,
        max_pages=max_pages,
        merge_from=merge_from,
    )
    try:
        report = run_collect(opts)
    except TypeSafeConfigError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(2) from e
    console.print_json(report.model_dump_json())
    if report.overall == "failed":
        raise SystemExit(1)


@main.group()
def review() -> None:
    """Human curation commands."""


@review.command("list")
def review_list() -> None:
    svc = ReviewService()
    items = svc.list_queue()
    table = Table(title=f"review queue ({len(items)})")
    table.add_column("id")
    table.add_column("status")
    table.add_column("title")
    for r in items:
        table.add_row(r.id, r.editorial_status.value, r.original_title[:60])
    console.print(table)


@review.command("show")
@click.argument("resource_id")
def review_show(resource_id: str) -> None:
    try:
        r = ReviewService().show(resource_id)
    except ReviewError as e:
        raise SystemExit(str(e)) from e
    console.print_json(r.model_dump_json())


@review.command("approve")
@click.argument("resource_id")
@click.option("--reviewer", required=True, help="Audit name only — not an auth credential.")
@click.option("--note", default=None)
def review_approve(resource_id: str, reviewer: str, note: str | None) -> None:
    try:
        r = ReviewService().approve(resource_id, reviewer=reviewer, note=note)
    except ReviewError as e:
        raise SystemExit(str(e)) from e
    console.print(f"approved {r.id} → curated (reviewer audit={reviewer})")


@review.command("reject")
@click.argument("resource_id")
@click.option("--reason", required=True)
@click.option("--reviewer", default=None)
def review_reject(resource_id: str, reason: str, reviewer: str | None) -> None:
    try:
        r = ReviewService().reject(resource_id, reason=reason, reviewer=reviewer)
    except ReviewError as e:
        raise SystemExit(str(e)) from e
    console.print(f"rejected {r.id}")


@review.command("propose")
@click.argument("resource_id")
def review_propose(resource_id: str) -> None:
    r = ReviewService().propose(resource_id)
    console.print(f"proposed {r.id}")


@review.command("archive")
@click.argument("resource_id")
@click.option("--reason", required=True)
def review_archive(resource_id: str, reason: str) -> None:
    try:
        r = ReviewService().archive(resource_id, reason=reason)
    except ReviewError as e:
        raise SystemExit(str(e)) from e
    console.print(f"archived {r.id}")


@main.command()
@click.option("--check", is_flag=True, help="Exit non-zero if generated files drift.")
def render(check: bool) -> None:
    """Generate README and category pages deterministically."""
    changed = Renderer().write(check=check)
    if check:
        console.print("render --check ok")
    else:
        console.print(f"render wrote/updated {len(changed)} files")
        for c in changed:
            console.print(f"  {c}")


@main.command()
@click.option("--previous-complete-week", "prev_week", is_flag=True, default=True)
def weekly(prev_week: bool) -> None:
    _ = prev_week
    path = write_weekly()
    console.print(f"weekly → {path}")


@main.group()
def site() -> None:
    """Static site generation."""


@site.command("build")
def site_build() -> None:
    cfg = AppConfig.load()
    out = build_site(base_path=cfg.runtime.site_base_path)
    console.print(f"site → {out}")


if __name__ == "__main__":
    main()
