from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from jev_awesome.automation.checkpoint import CheckpointStore
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
from jev_awesome.sources.github import GitHubDiscoveryAdapter
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
    adapters = []
    gh_cfg = (src_cfg.get("github_discovery") or {}) if isinstance(src_cfg, dict) else {}
    adapters.append(
        GitHubDiscoveryAdapter(
            queries=gh_cfg.get("queries"),
            enabled=gh_cfg.get("enabled", True),
        )
    )
    rss_cfg = src_cfg.get("rss_atom") or {}
    adapters.append(
        RssAtomAdapter(
            feeds=rss_cfg.get("feeds") or [],
            enabled=rss_cfg.get("enabled", True),
        )
    )
    off_cfg = src_cfg.get("official_monitor") or {}
    adapters.append(
        OfficialMonitorAdapter(
            pages=off_cfg.get("pages") or [],
            enabled=off_cfg.get("enabled", True),
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
    seen_round: set[str] = set()

    for adapter in adapters:
        try:
            resources, result = adapter.collect(ctx)
        except Exception as e:  # noqa: BLE001
            result = SourceResult(
                source_id=getattr(adapter, "source_id", "unknown"),
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

            decision = store.get_decision(resource.id)
            if decision and decision.decision == "rejected":
                if decision.content_hash and decision.content_hash == resource.content_hash:
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
            if decision and decision.decision == "merged":
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
