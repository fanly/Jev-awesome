from __future__ import annotations

from datetime import UTC, datetime

from jev_awesome.models import (
    EditorialStatus,
    JevRelationship,
    OfficialStatus,
    PrimaryCategory,
    Resource,
    ResourceKind,
    VerificationLevel,
)
from jev_awesome.normalize import content_hash


def make_resource(**kwargs) -> Resource:
    now = datetime.now(UTC)
    base = dict(
        id="github:1",
        resource_kind=ResourceKind.SDK,
        primary_category=PrimaryCategory.SDK_INTEGRATIONS,
        canonical_url="https://github.com/acme/demo",
        original_title="acme/demo",
        first_discovered_at=now,
        editorial_status=EditorialStatus.PENDING,
        verification_level=VerificationLevel.DISCOVERED,
        official_status=OfficialStatus.UNKNOWN,
        jev_relationship=JevRelationship.UNCLEAR,
        content_hash=content_hash("x"),
    )
    base.update(kwargs)
    return Resource.model_validate(base)
