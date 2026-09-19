from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from jev_awesome.classification import apply_suggestion_fields, build_classifier
from jev_awesome.config import AppConfig
from jev_awesome.dates import utc_now
from jev_awesome.dedupe import find_duplicate, merge_machine_fields, title_similarity_suggestion
from jev_awesome.models import (
    CatalogEvent,
    ClassifierMode,
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
    report = RunReport(
        run_id=run_id,
        started_at=started,
        mode=opts.mode,
        classifier=opts.classifier,
        dry_run=opts.dry_run,
        write_local=opts.write_local,
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

    for adapter in adapters:
        try:
            resources, result = adapter.collect(ctx)
        except Exception as e:  # noqa: BLE001
            result = SourceResult(
                source_id=getattr(adapter, "source_id", "unknown"),
                status="failed",
                error=str(e),
            )
            resources = []
            # Critical: do not clear existing data
            report.notes.append(f"source_exception_kept_existing:{result.source_id}")
        all_results.append(result)

        for resource in resources:
            # Skip if previously rejected with same hash
            decision = store.get_decision(resource.id)
            if decision and decision.decision == "rejected":
                if decision.content_hash and decision.content_hash == resource.content_hash:
                    result.duplicates += 1
                    continue
                report.notes.append(f"rejected_revisit_suggested:{resource.id}")

            dup = find_duplicate(resource, existing)
            if dup:
                result.duplicates += 1
                merged = merge_machine_fields(dup, resource)
                # Classify suggestion on merge target
                try:
                    suggestion = classifier.classify(merged)
                    if opts.classifier != ClassifierMode.RULES:
                        model_calls += 1
                    merged = apply_suggestion_fields(merged, suggestion)
                except Exception as e:  # noqa: BLE001
                    report.notes.append(f"classify_failed:{merged.id}:{e}")
                if opts.write_local and not opts.dry_run:
                    inbox = merged.editorial_status in {
                        EditorialStatus.PENDING,
                        EditorialStatus.PROPOSED,
                    }
                    store.save_resource(merged, inbox=inbox)
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

            # New candidates stay pending
            resource = resource.model_copy(
                update={"editorial_status": EditorialStatus.PENDING}
            )
            existing.append(resource)
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

    report.sources = all_results
    report.model_calls = model_calls
    report.finished_at = utc_now()
    if any(s.status == "failed" for s in all_results) and any(
        s.status == "success" for s in all_results
    ):
        report.overall = "degraded"
    elif all(s.status == "failed" for s in all_results if s.status != "skipped"):
        live = [s for s in all_results if s.status != "skipped"]
        report.overall = "failed" if live else "success"
    elif any(s.status == "degraded" for s in all_results):
        report.overall = "degraded"
    else:
        report.overall = "success"

    # Always persist report to reports/ (preview OK even in dry-run)
    store.save_report(report)
    # Also write a latest pointer-style copy for humans
    latest = config.paths.reports / "latest.json"
    latest.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return report
