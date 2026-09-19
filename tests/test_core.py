from __future__ import annotations

from datetime import UTC, datetime

from jev_awesome.dedupe import find_duplicate, merge_machine_fields
from jev_awesome.models import EditorialStatus, ResourceKind
from jev_awesome.normalize import normalize_url
from jev_awesome.rendering.render import Renderer
from tests.helpers import make_resource


def test_t01_render_idempotent(store, tmp_paths):
    r = make_resource(
        id="github:10",
        editorial_status=EditorialStatus.CURATED,
        summary_zh="摘要",
        jev_role="角色",
        developer_value="价值",
    )
    store.save_resource(r, inbox=False)
    renderer = Renderer(store=store, paths=tmp_paths)
    renderer.write()
    first = (tmp_paths.root / "README.md").read_bytes()
    renderer.write()
    second = (tmp_paths.root / "README.md").read_bytes()
    assert first == second


def test_t02_same_repo_url_case_merge():
    a = make_resource(
        id="github:42",
        github_repo_id=42,
        github_full_name="Acme/Demo",
        canonical_url="https://GitHub.com/Acme/Demo",
    )
    b = make_resource(
        id="github:42",
        github_repo_id=42,
        github_full_name="acme/demo",
        canonical_url="https://github.com/acme/demo/",
    )
    assert find_duplicate(b, [a]) is a
    assert normalize_url(a.canonical_url) == normalize_url(
        "https://github.com/Acme/Demo?utm_source=x"
    )


def test_t03_different_owners_same_name_not_merged():
    a = make_resource(
        id="github:1",
        github_repo_id=1,
        github_full_name="alice/jev",
        canonical_url="https://github.com/alice/jev",
    )
    b = make_resource(
        id="github:2",
        github_repo_id=2,
        github_full_name="bob/jev",
        canonical_url="https://github.com/bob/jev",
    )
    assert find_duplicate(b, [a]) is None


def test_t09_editorial_not_overwritten_by_machine_merge():
    human = make_resource(
        id="github:7",
        summary_zh="人工摘要",
        jev_role="人工角色",
        editorial_status=EditorialStatus.PROPOSED,
        resource_kind=ResourceKind.SDK,
    )
    machine = make_resource(
        id="github:7",
        summary_zh="机器想覆盖",
        jev_role="机器角色",
        original_title="new-title",
        github_full_name="acme/demo",
    )
    merged = merge_machine_fields(human, machine)
    assert merged.summary_zh == "人工摘要"
    assert merged.jev_role == "人工角色"
    assert merged.github_full_name == "acme/demo"


def test_t11_reproduced_requires_evidence():
    import pytest
    from pydantic import ValidationError

    from jev_awesome.models import VerificationLevel

    with pytest.raises(ValidationError):
        make_resource(verification_level=VerificationLevel.REPRODUCED)


def test_t11b_reproduced_with_evidence_ok():
    from jev_awesome.models import EvidenceItem, VerificationLevel

    r = make_resource(
        verification_level=VerificationLevel.REPRODUCED,
        evidence=[
            EvidenceItem(
                url="https://example.com",
                source_type="run",
                checked_at=datetime.now(UTC),
                supports="reproduction log",
                code_location="tests/test_demo.py:10",
            )
        ],
    )
    assert r.verification_level.value == "reproduced"


def test_t29_uncurated_not_in_curated_render(store, tmp_paths):
    store.save_resource(
        make_resource(id="github:99", editorial_status=EditorialStatus.PENDING),
        inbox=True,
    )
    renderer = Renderer(store=store, paths=tmp_paths)
    out = renderer.render_all()
    assert "curated=0" in out["README.md"]
