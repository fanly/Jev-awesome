from __future__ import annotations

from jev_awesome.dates import utc_now
from jev_awesome.models import (
    CatalogEvent,
    Decision,
    EditorialStatus,
    Resource,
    ReviewRecord,
)
from jev_awesome.normalize import content_hash
from jev_awesome.store import CatalogStore


class ReviewError(ValueError):
    pass


REQUIRED_FOR_APPROVE = ("summary_zh", "jev_role", "developer_value", "primary_category")


class ReviewService:
    def __init__(self, store: CatalogStore | None = None) -> None:
        self.store = store or CatalogStore()

    def list_queue(self, *, include_proposed: bool = True) -> list[Resource]:
        items = self.store.list_resources(status_dir="inbox")
        statuses = {EditorialStatus.PENDING, EditorialStatus.PROPOSED}
        if not include_proposed:
            statuses = {EditorialStatus.PENDING}
        return [r for r in items if r.editorial_status in statuses]

    def show(self, resource_id: str) -> Resource:
        r = self.store.get_resource(resource_id)
        if r is None:
            raise ReviewError(f"resource not found: {resource_id}")
        return r

    def approve(
        self,
        resource_id: str,
        *,
        reviewer: str,
        note: str | None = None,
    ) -> Resource:
        """Approve moves to curated. reviewer is audit metadata only."""
        r = self.show(resource_id)
        missing = [f for f in REQUIRED_FOR_APPROVE if not getattr(r, f)]
        if missing:
            raise ReviewError(f"missing required fields for approve: {', '.join(missing)}")
        if r.editorial_status == EditorialStatus.REJECTED:
            raise ReviewError("rejected items must be restored before approve")
        now = utc_now()
        updated = r.model_copy(
            update={
                "editorial_status": EditorialStatus.CURATED,
                "review_record": ReviewRecord(
                    reviewer=reviewer,
                    reviewed_at=now,
                    decision="approve",
                    reason=note,
                ),
                "last_material_change_at": now,
            }
        )
        self.store.save_resource(updated, inbox=False)
        event = CatalogEvent(
            id=f"evt-accept-{content_hash(resource_id + now.isoformat())[:12]}",
            event_type="human_accepted",
            resource_id=resource_id,
            occurred_at=now,
            summary=f"Accepted by reviewer={reviewer} (audit only)",
            material=True,
        )
        self.store.save_event(event)
        return updated

    def reject(self, resource_id: str, *, reason: str, reviewer: str | None = None) -> Resource:
        if not reason.strip():
            raise ReviewError("reject requires a reason")
        r = self.show(resource_id)
        now = utc_now()
        updated = r.model_copy(
            update={
                "editorial_status": EditorialStatus.REJECTED,
                "review_record": ReviewRecord(
                    reviewer=reviewer,
                    reviewed_at=now,
                    decision="reject",
                    reason=reason,
                ),
            }
        )
        self.store.save_resource(updated, inbox=False)
        self.store.save_decision(
            Decision(
                resource_id=resource_id,
                decision="rejected",
                reason=reason,
                decided_at=now,
                content_hash=r.content_hash,
                actor=reviewer,
            )
        )
        return updated

    def propose(self, resource_id: str) -> Resource:
        r = self.show(resource_id)
        updated = r.model_copy(update={"editorial_status": EditorialStatus.PROPOSED})
        self.store.save_resource(updated, inbox=True)
        return updated

    def archive(self, resource_id: str, *, reason: str) -> Resource:
        r = self.show(resource_id)
        if r.editorial_status != EditorialStatus.CURATED:
            raise ReviewError("only curated items can be archived")
        now = utc_now()
        updated = r.model_copy(
            update={
                "editorial_status": EditorialStatus.ARCHIVED,
                "review_record": ReviewRecord(
                    reviewed_at=now,
                    decision="archive",
                    reason=reason,
                ),
            }
        )
        self.store.save_resource(updated, inbox=False)
        self.store.save_decision(
            Decision(
                resource_id=resource_id,
                decision="archived",
                reason=reason,
                decided_at=now,
                content_hash=r.content_hash,
            )
        )
        return updated

    def restore(self, resource_id: str) -> Resource:
        r = self.show(resource_id)
        updated = r.model_copy(update={"editorial_status": EditorialStatus.PROPOSED})
        self.store.save_resource(updated, inbox=True)
        self.store.save_decision(
            Decision(
                resource_id=resource_id,
                decision="restored",
                reason="restored_for_re_review",
                decided_at=utc_now(),
                content_hash=r.content_hash,
            )
        )
        return updated

    def merge_duplicate(
        self, keep_id: str, drop_id: str, *, reason: str, reviewer: str | None = None
    ) -> Resource:
        keep = self.show(keep_id)
        drop = self.show(drop_id)
        now = utc_now()
        aliases = list(dict.fromkeys([*keep.aliases, drop.canonical_url, *drop.aliases]))
        merged = keep.model_copy(update={"aliases": aliases})
        self.store.save_resource(merged)
        dropped = drop.model_copy(
            update={
                "editorial_status": EditorialStatus.REJECTED,
                "review_record": ReviewRecord(
                    reviewer=reviewer,
                    reviewed_at=now,
                    decision="merge",
                    reason=reason,
                ),
            }
        )
        self.store.save_resource(dropped, inbox=False)
        self.store.save_decision(
            Decision(
                resource_id=drop_id,
                decision="merged",
                reason=reason,
                decided_at=now,
                content_hash=drop.content_hash,
                merged_into=keep_id,
                actor=reviewer,
            )
        )
        return merged
