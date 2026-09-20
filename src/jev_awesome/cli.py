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
        (
            "GITHUB_TOKEN/GH_TOKEN",
            "present"
            if (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
            else "absent",
        ),
        ("classifier_mode_default", config.runtime.classifier_mode),
        ("collector_enabled", str(config.runtime.collector_enabled)),
        ("auto_pr_enabled", str(config.runtime.auto_pr_enabled)),
        ("pages_enabled", str(config.runtime.pages_enabled)),
        (
            "JEV_ALLOW_FAKE_IP",
            "ON"
            if os.environ.get("JEV_ALLOW_FAKE_IP", "").lower() in {"1", "true", "yes", "on"}
            else "off(default)",
        ),
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
@click.option(
    "--mode",
    default="incremental",
    type=click.Choice(["incremental", "refresh", "maintenance", "all"]),
)
@click.option("--classifier", default="rules", type=click.Choice(["rules", "auto", "typesafe"]))
@click.option(
    "--dry-run/--write-preview-only", default=True, help="Default dry-run; no catalog writes."
)
@click.option("--write-local", is_flag=True, help="Write local catalog files (still no remote).")
@click.option("--max-pages", default=2, show_default=True)
@click.option(
    "--merge-from",
    type=click.Path(path_type=Path),
    default=None,
    help="Merge unmerged robot branch checkout.",
)
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


@main.group()
def payload() -> None:
    """Catalog payload export/import between collect and publish jobs."""


@payload.command("export")
@click.option("--out", "out_dir", type=click.Path(path_type=Path), required=True)
@click.option("--repository", default="fanly/Jev-awesome", show_default=True)
@click.option("--source-sha", default=None)
@click.option("--run-id", default=None)
@click.option("--attempt", default=None, type=int)
def payload_export(
    out_dir: Path,
    repository: str,
    source_sha: str | None,
    run_id: str | None,
    attempt: int | None,
) -> None:
    """Export allowlisted inbox candidates to a catalog payload directory."""
    import os
    import subprocess

    from jev_awesome.automation.payload import export_catalog_payload

    root = _paths().root
    sha = source_sha
    if not sha:
        try:
            sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            sha = None
    meta = {
        "repository": repository,
        "source_sha": sha,
        "run_id": run_id or os.environ.get("GITHUB_RUN_ID"),
        "attempt": attempt
        if attempt is not None
        else (
            int(os.environ["GITHUB_RUN_ATTEMPT"])
            if os.environ.get("GITHUB_RUN_ATTEMPT", "").isdigit()
            else None
        ),
    }
    path = export_catalog_payload(root, out_dir=out_dir, meta=meta)
    console.print(f"payload exported → {path}")


@main.command("publish")
@click.option("--enabled/--disabled", default=False, help="Must pass --enabled; default skips.")
@click.option("--dry-run/--no-dry-run", default=True, help="Default dry-run: no push/PR.")
@click.option("--remote", default="origin", show_default=True)
@click.option("--merge-from", type=click.Path(path_type=Path), default=None)
@click.option(
    "--payload",
    "payload_dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Import catalog payload before publish (required on CI publish path).",
)
@click.option("--owner", default="fanly")
@click.option("--repo", default="Jev-awesome")
@click.option(
    "--expected-source-sha",
    default=None,
    help="Trusted collect tip SHA (or EXPECTED_SOURCE_SHA env).",
)
@click.option(
    "--expected-run-id",
    default=None,
    help="Trusted collect run id (or EXPECTED_RUN_ID env).",
)
@click.option(
    "--expected-producer-attempt",
    default=None,
    help="Trusted collect attempt (or EXPECTED_PRODUCER_ATTEMPT env).",
)
@click.option(
    "--actual-checkout-sha",
    default=None,
    help="Publish checkout SHA (or ACTUAL_CHECKOUT_SHA env / git HEAD).",
)
def publish_cmd(
    enabled: bool,
    dry_run: bool,
    remote: str,
    merge_from: Path | None,
    payload_dir: Path | None,
    owner: str,
    repo: str,
    expected_source_sha: str | None,
    expected_run_id: str | None,
    expected_producer_attempt: str | None,
    actual_checkout_sha: str | None,
) -> None:
    """Publish allowlisted catalog changes to robot branch and open/update PR."""
    from dataclasses import asdict

    from jev_awesome.automation.github_transport import HttpxGitHubTransport
    from jev_awesome.automation.payload import PayloadError, import_catalog_payload
    from jev_awesome.automation.publisher import Publisher, PublishOptions
    from jev_awesome.store import CatalogStore

    root = _paths().root
    expected_repo = f"{owner}/{repo}"
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    transport = HttpxGitHubTransport(token=token or "dry-run-unused")
    opts = PublishOptions(
        enabled=enabled,
        dry_run=dry_run,
        remote_name=remote,
        owner=owner,
        repo=repo,
        expected_repo=expected_repo,
        require_payload=payload_dir is not None,
    )

    # G2: dry-run / disabled must return BEFORE payload import / merge_from / mutation
    if (not enabled) or dry_run:
        result = Publisher(root, transport=transport, opts=opts).publish()
        console.print_json(data=asdict(result))
        return

    if not token:
        console.print("[red]GITHUB_TOKEN required for non-dry-run publish[/red]")
        raise SystemExit(2)

    if payload_dir is not None:
        if not payload_dir.exists():
            console.print(f"[red]payload required but missing: {payload_dir}[/red]")
            raise SystemExit(1)
        src_sha = expected_source_sha or os.environ.get("EXPECTED_SOURCE_SHA")
        run_id = expected_run_id or os.environ.get("EXPECTED_RUN_ID")
        attempt = expected_producer_attempt or os.environ.get("EXPECTED_PRODUCER_ATTEMPT")
        checkout = actual_checkout_sha or os.environ.get("ACTUAL_CHECKOUT_SHA")
        if not checkout:
            import subprocess

            try:
                checkout = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, text=True
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                checkout = None
        if not src_sha or not run_id or not attempt or not checkout:
            console.print(
                "[red]EXPECTED_SOURCE_SHA, EXPECTED_RUN_ID, EXPECTED_PRODUCER_ATTEMPT "
                "(and checkout SHA) required for live payload publish[/red]"
            )
            raise SystemExit(2)
        try:
            imported = import_catalog_payload(
                payload_dir,
                root,
                expected_repo=expected_repo,
                expected_source_sha=src_sha,
                expected_run_id=run_id,
                expected_producer_attempt=attempt,
                actual_checkout_sha=checkout,
                require_trusted_identity=True,
            )
        except PayloadError as e:
            console.print(f"[red]payload import failed: {e}[/red]")
            raise SystemExit(1) from e
        console.print(f"payload imported resources={imported.imported}")

    if merge_from and merge_from.exists():
        CatalogStore(Paths(root)).merge_catalog_from_branch_files(merge_from)

    result = Publisher(root, transport=transport, opts=opts).publish()
    console.print_json(data=asdict(result))
    if result.status == "failed":
        raise SystemExit(1)
    if result.status == "paused":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
