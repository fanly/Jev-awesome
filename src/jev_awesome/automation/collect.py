from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from jev_awesome.automation.checkpoint import CheckpointStore
from jev_awesome.automation.source_planner import SourceCheckpointStore, plan_source
from jev_awesome.classification import apply_suggestion_fields, build_classifier
from jev_awesome.config import AppConfig
from jev_awesome.dates import utc_now
from jev_awesome.dedupe import find_duplicate, merge_machine_fields, title_similarity_suggestion
from jev_awesome.models import (
    CatalogEvent,
    ClassifierMode,
    Disposition,
    EditorialStatus,
    RunReport,
    SourceResult,
)
from jev_awesome.normalize import content_hash
from jev_awesome.sources import CollectContext
from jev_awesome.sources.awesome import AwesomeRadarAdapter
from jev_awesome.sources.github import GitHubDiscoveryAdapter
from jev_awesome.sources.known_repos import KnownRepoWatchAdapter
from jev_awesome.sources.official import OfficialMonitorAdapter
from jev_awesome.sources.rss import RssAtomAdapter
from jev_awesome.store import CatalogStore


@dataclass
class CollectOptions:
    mode: str = "incremental"
    classifier: ClassifierMode = ClassifierMode.RULES
    dry_run: bool = True
    write_local: bool = False
    max_pages: int = 2
    merge_from: Path | None = None
    force: bool = False


def _source_cfg(src_cfg: dict, key: str) -> dict:
    raw = src_cfg.get(key) or {}
    return raw if isinstance(raw, dict) else {}


def run_collect(opts: CollectOptions, config: AppConfig | None = None) -> RunReport:
    config = config or AppConfig.load()
    store = CatalogStore(config.paths)
    started = utc_now()
    run_id = f"run-{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    counts_before = store.counts()
    report = RunReport(
        run_id=run_id,
        started_at=started,
        mode=opts.mode,
        classifier=opts.classifier,
        dry_run=opts.dry_run,
        write_local=opts.write_local,
        counts_before=counts_before,
    )

    if opts.merge_from and opts.merge_from.exists():
        n = store.merge_catalog_from_branch_files(opts.merge_from)
        report.notes.append(f"merged_unmerged_branch_files:{n}")

    src_cfg = config.sources.get("sources") or config.sources
    if not isinstance(src_cfg, dict):
        src_cfg = {}

    curated = [
        r
        for r in store.list_resources(status_dir="resources")
        if r.editorial_status == EditorialStatus.CURATED
    ]

    # Known-repo previous snapshots (optional durable file)
    snap_path = config.paths.automation / "known_repo_snapshots.json"
    previous_snapshots: dict = {}
    if snap_path.exists():
        try:
            previous_snapshots = json.loads(snap_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous_snapshots = {}

    adapters: list[tuple[dict, object]] = []
    gh_cfg = _source_cfg(src_cfg, "github_discovery")
    adapters.append(
        (
            gh_cfg,
            GitHubDiscoveryAdapter(
                queries=gh_cfg.get("queries"),
                enabled=gh_cfg.get("enabled", True),
            ),
        )
    )
    kr_cfg = _source_cfg(src_cfg, "known_repo_watch")
    known_adapter = KnownRepoWatchAdapter(
        repos=kr_cfg.get("repos") or [],
        curated_resources=curated,
        previous_snapshots=previous_snapshots,
        enabled=bool(kr_cfg) and kr_cfg.get("enabled", True),
    )
    adapters.append((kr_cfg, known_adapter))
    rss_cfg = _source_cfg(src_cfg, "rss_atom")
    adapters.append(
        (
            rss_cfg,
            RssAtomAdapter(
                feeds=rss_cfg.get("feeds") or [],
                enabled=rss_cfg.get("enabled", True),
            ),
        )
    )
    off_cfg = _source_cfg(src_cfg, "official_monitor")
    adapters.append(
        (
            off_cfg,
            OfficialMonitorAdapter(
                pages=off_cfg.get("pages") or [],
                enabled=off_cfg.get("enabled", True),
                cache_dir=config.paths.cache / "http" / "official",
            ),
        )
    )
    aw_cfg = _source_cfg(src_cfg, "awesome_radar")
    adapters.append(
        (
            aw_cfg,
            AwesomeRadarAdapter(
                lists=aw_cfg.get("lists") or [],
                enabled=bool(aw_cfg) and aw_cfg.get("enabled", True),
            ),
        )
    )

    ctx = CollectContext(
        dry_run=opts.dry_run,
        write_local=opts.write_local,
        token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        max_pages=opts.max_pages,
    )

    classifier = build_classifier(opts.classifier)
    if opts.classifier == ClassifierMode.TYPESAFE:
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            from jev_awesome.classification.typesafe_adapter import TypeSafeConfigError

            raise TypeSafeConfigError(
                "TYPESAFE_API_KEY is required for classifier mode typesafe; "
                "refusing to pretend the API is connected"
            )
    model_calls = 0
    existing = store.all_known()
    all_results: list[SourceResult] = []
    dispositions: list[Disposition] = []
    checkpoints = CheckpointStore(config.paths.cache / "checkpoints")
    source_cps = SourceCheckpointStore(config.paths.automation / "source_checkpoints.json")
    seen_round: set[str] = set()

    for src_meta, adapter in adapters:
        source_id = getattr(adapter, "source_id", "unknown")
        frequency = src_meta.get("frequency")
        decision = plan_source(
            now=started,
            frequency=frequency,
            last_successful_at=source_cps.last_successful_at(source_id),
            mode=opts.mode,
            force=opts.force,
            dry_run=opts.dry_run,
        )
        if not decision.should_run:
            all_results.append(
                SourceResult(
                    source_id=source_id,
                    status="skipped",
                    execution_status="skipped",
                    coverage_status="unknown",
                    error=f"not_due:{decision.reason}",
                )
            )
            report.notes.append(f"source_skipped_not_due:{source_id}:{decision.reason}")
            continue
        if decision.status.value in {"forced", "backfill"}:
            report.notes.append(f"source_plan:{source_id}:{decision.status.value}")

        try:
            resources, result = adapter.collect(ctx)
        except Exception as e:  # noqa: BLE001
            result = SourceResult(
                source_id=source_id,
                status="failed",
                execution_status="failed",
                coverage_status="unknown",
                error=str(e),
            )
            resources = []
            report.notes.append(f"source_exception_kept_existing:{result.source_id}")
        all_results.append(result)

        shard_ok = result.status in {"success", "degraded"} and (
            result.coverage_status in {"complete", "partial", None}
        )
        # Advance checkpoint only after durable write of this source's outcomes
        durable_saved = False

        for resource in resources:
            if resource.id in seen_round:
                dispositions.append(
                    Disposition(
                        resource_id=resource.id,
                        disposition="duplicate_in_round",
                        source_id=result.source_id,
                    )
                )
                result.duplicates += 1
                continue
            seen_round.add(resource.id)

            decision_rec = store.get_decision(resource.id)
            if decision_rec and decision_rec.decision == "rejected":
                if decision_rec.content_hash and decision_rec.content_hash == resource.content_hash:
                    result.duplicates += 1
                    dispositions.append(
                        Disposition(
                            resource_id=resource.id,
                            disposition="suppressed_rejected",
                            source_id=result.source_id,
                        )
                    )
                    continue
                report.notes.append(f"rejected_revisit_suggested:{resource.id}")
            if decision_rec and decision_rec.decision == "merged":
                dispositions.append(
                    Disposition(
                        resource_id=resource.id,
                        disposition="suppressed_merged",
                        source_id=result.source_id,
                    )
                )
                continue

            dup = find_duplicate(resource, existing)
            if dup:
                result.duplicates += 1
                before_hash = dup.content_hash
                merged = merge_machine_fields(dup, resource)
                try:
                    suggestion = classifier.classify(merged)
                    if opts.classifier != ClassifierMode.RULES:
                        model_calls += 1
                    merged = apply_suggestion_fields(merged, suggestion)
                except Exception as e:  # noqa: BLE001
                    report.notes.append(f"classify_failed:{merged.id}:{e}")
                unchanged = (
                    merged.content_hash == before_hash and merged.suggestion == dup.suggestion
                )
                disp = "unchanged" if unchanged else "updated"
                dispositions.append(
                    Disposition(resource_id=merged.id, disposition=disp, source_id=result.source_id)
                )
                if opts.write_local and not opts.dry_run:
                    inbox = merged.editorial_status in {
                        EditorialStatus.PENDING,
                        EditorialStatus.PROPOSED,
                    }
                    store.save_resource(merged, inbox=inbox)
                    durable_saved = True
                # refresh existing list entry
                for i, ex in enumerate(existing):
                    if ex.id == merged.id:
                        existing[i] = merged
                        break
                continue

            sug = title_similarity_suggestion(resource, existing)
            try:
                suggestion = classifier.classify(resource)
                if opts.classifier != ClassifierMode.RULES:
                    model_calls += getattr(classifier, "request_count", 1)
                resource = apply_suggestion_fields(resource, suggestion)
            except Exception as e:  # noqa: BLE001
                report.notes.append(f"classify_failed:{resource.id}:{e}")

            if sug:
                report.notes.append(
                    f"similar_title_suggestion:{sug.left_id}->{sug.right_id}:{sug.reason}"
                )

            resource = resource.model_copy(update={"editorial_status": EditorialStatus.PENDING})
            existing.append(resource)
            dispositions.append(
                Disposition(
                    resource_id=resource.id,
                    disposition="created",
                    source_id=result.source_id,
                )
            )
            if opts.write_local and not opts.dry_run:
                store.save_resource(resource, inbox=True)
                store.save_event(
                    CatalogEvent(
                        id=f"evt-disc-{content_hash(resource.id)[:12]}",
                        event_type="first_discovered",
                        resource_id=resource.id,
                        occurred_at=resource.first_discovered_at,
                        summary=f"Discovered via {result.source_id}",
                        material=False,
                    )
                )
                durable_saved = True

        # Persist material events from known_repo_watch (never auto-curate)
        if (
            isinstance(adapter, KnownRepoWatchAdapter)
            and opts.write_local
            and not opts.dry_run
            and adapter.material_events
        ):
            for evt in adapter.material_events:
                store.save_event(evt)
                durable_saved = True
            if adapter.new_snapshots:
                from jev_awesome.atomic_io import atomic_write_text

                atomic_write_text(
                    snap_path,
                    json.dumps(adapter.new_snapshots, indent=2) + "\n",
                )

        # Checkpoint: only if source shard succeeded enough AND durable (or no writes needed)
        cov = result.coverage_status or "unknown"
        # Failed shards must NOT advance
        if result.execution_status == "failed" or result.status == "failed":
            report.notes.append(f"checkpoint_not_advanced:{result.source_id}:failed_shard")
        elif opts.dry_run:
            report.notes.append(f"checkpoint_not_advanced:{result.source_id}:dry_run")
        elif not opts.write_local:
            report.notes.append(f"checkpoint_not_advanced:{result.source_id}:no_write_local")
        elif durable_saved or result.status == "success":
            # Success with zero new items still advances if coverage known and writes attempted path ok
            if shard_ok and cov != "unknown":
                cursor = None
                if result.queries:
                    last_q = result.queries[-1]
                    cursor = f"pages={last_q.pages_read};items={last_q.items_returned}"
                checkpoints.save(
                    result.source_id,
                    cursor=cursor,
                    coverage_status=cov,
                    durable=True,
                    dry_run=False,
                    meta={"run_id": run_id},
                )
                source_cps.record_success(
                    result.source_id,
                    at=utc_now(),
                    coverage_status=cov,
                    dry_run=False,
                    meta={"run_id": run_id},
                )
            else:
                report.notes.append(f"checkpoint_not_advanced:{result.source_id}:coverage={cov}")

    report.sources = all_results
    report.dispositions = dispositions
    report.model_calls = model_calls
    report.finished_at = utc_now()
    report.counts_after = (
        store.counts() if (opts.write_local and not opts.dry_run) else counts_before
    )

    if any(s.status == "failed" for s in all_results) and any(
        s.status == "success" for s in all_results
    ):
        report.overall = "degraded"
    elif all(s.status == "failed" for s in all_results if s.status != "skipped"):
        live = [s for s in all_results if s.status != "skipped"]
        report.overall = "failed" if live else "success"
    elif any(s.status == "degraded" for s in all_results):
        report.overall = "degraded"
    elif any(s.coverage_status == "partial" for s in all_results):
        report.overall = "degraded"
        report.notes.append("overall_degraded_due_to_partial_coverage")
    else:
        report.overall = "success"

    store.save_report(report)
    latest = config.paths.reports / "latest.json"
    latest.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report
