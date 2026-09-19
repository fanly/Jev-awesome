from __future__ import annotations

import json

from jev_awesome.models import EditorialStatus
from jev_awesome.site.build import build_site
from tests.helpers import make_resource


def test_t28_site_base_path_and_index(store, tmp_paths):
    r = make_resource(
        id="github:88",
        editorial_status=EditorialStatus.CURATED,
        summary_zh="中文测试",
        jev_role="角色",
        developer_value="价值",
    )
    store.save_resource(r, inbox=False)
    out = build_site(store=store, paths=tmp_paths, base_path="/Jev-awesome/")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert 'href="/Jev-awesome/styles.css"' in html
    idx = json.loads((out / "search-index.json").read_text(encoding="utf-8"))
    assert idx["base_path"] == "/Jev-awesome/"
    assert idx["resources"][0]["summary_zh"] == "中文测试"
    assert (out / "r" / "github_88.html").exists()


def test_t10_rejected_same_hash_decision(store):
    from jev_awesome.curation.review import ReviewService
    from jev_awesome.normalize import content_hash

    r = make_resource(id="github:101", content_hash=content_hash("same"))
    store.save_resource(r, inbox=True)
    ReviewService(store).reject("github:101", reason="spam")
    d = store.get_decision("github:101")
    assert d is not None and d.content_hash == r.content_hash
