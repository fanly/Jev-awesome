from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.models import CATEGORY_META, EditorialStatus, PrimaryCategory, Resource
from jev_awesome.paths import Paths
from jev_awesome.rendering.radar import radar_highlights, render_radar_markdown
from jev_awesome.security import escape_md, safe_href
from jev_awesome.store import CatalogStore, load_yaml

GENERATED_START = "<!-- JEV-AWESOME:GENERATED-START -->"
GENERATED_END = "<!-- JEV-AWESOME:GENERATED-END -->"


def _sort_key(r: Resource) -> tuple:
    return (
        0 if r.official_status.value == "official" else 1,
        (r.original_title or "").lower(),
        r.id,
    )


def _load_featured_ids(paths: Paths) -> list[str]:
    featured_path = paths.config / "featured.yaml"
    if not featured_path.exists():
        return []
    data = load_yaml(featured_path)
    raw = data.get("homepage") or data.get("featured") or []
    return [str(x) for x in raw if x]


class Renderer:
    def __init__(self, store: CatalogStore | None = None, paths: Paths | None = None) -> None:
        self.store = store or CatalogStore()
        self.paths = paths or self.store.paths
        self.env = Environment(
            loader=FileSystemLoader(str(self.paths.templates)),
            autoescape=select_autoescape(enabled_extensions=("html", "xml")),
            keep_trailing_newline=True,
        )
        self.env.filters["md"] = escape_md

    def curated(self) -> list[Resource]:
        items = [
            r
            for r in self.store.list_resources(status_dir="resources")
            if r.editorial_status == EditorialStatus.CURATED
        ]
        featured_ids = _load_featured_ids(self.paths)
        if not featured_ids:
            return sorted(items, key=_sort_key)
        rank = {rid: i for i, rid in enumerate(featured_ids)}

        def key(r: Resource) -> tuple:
            if r.id in rank:
                return (0, rank[r.id], r.id)
            return (1, *_sort_key(r))

        return sorted(items, key=key)

    def featured(self, curated: list[Resource] | None = None) -> list[Resource]:
        curated = curated if curated is not None else self.curated()
        featured_ids = _load_featured_ids(self.paths)
        if not featured_ids:
            return curated[:10]
        by_id = {r.id: r for r in curated}
        out = [by_id[i] for i in featured_ids if i in by_id]
        return out[:10]

    def proposed(self) -> list[Resource]:
        return sorted(
            [r for r in self.store.all_known() if r.editorial_status == EditorialStatus.PROPOSED],
            key=_sort_key,
        )

    def render_all(self) -> dict[str, str]:
        curated = self.curated()
        featured = self.featured(curated)
        proposed = self.proposed()
        counts = self.store.counts()
        by_cat: dict[PrimaryCategory, list[Resource]] = {c: [] for c in PrimaryCategory}
        for r in curated:
            if r.primary_category:
                by_cat[r.primary_category].append(r)

        highlights = radar_highlights(self.store, limit=5)
        ctx = {
            "curated": curated,
            "featured": featured,
            "proposed": proposed,
            "counts": counts,
            "by_category": by_cat,
            "category_meta": CATEGORY_META,
            "generated_start": GENERATED_START,
            "generated_end": GENERATED_END,
            "safe_href": safe_href,
            "radar_highlights": highlights,
            "radar_label": "自动发现 · 未精选",
        }
        outputs: dict[str, str] = {}
        outputs["README.md"] = self.env.get_template("README.md.j2").render(**ctx)
        outputs["README.en.md"] = self.env.get_template("README.en.md.j2").render(**ctx)
        for cat, meta in CATEGORY_META.items():
            outputs[f"docs/categories/{meta['slug']}.md"] = self.env.get_template(
                "category.md.j2"
            ).render(category=cat, meta=meta, items=by_cat[cat], **ctx)
        outputs["docs/radar/latest.md"] = render_radar_markdown(self.store)
        return outputs

    def write(self, *, check: bool = False) -> list[str]:
        outputs = self.render_all()
        changed: list[str] = []
        mismatched: list[str] = []
        for rel, content in sorted(outputs.items()):
            path = self.paths.root / rel
            if path.exists():
                existing = path.read_text(encoding="utf-8")
                if GENERATED_START in existing and GENERATED_END in existing:
                    content = _splice_generated(existing, content)
            if check:
                if not path.exists() or path.read_text(encoding="utf-8") != content:
                    mismatched.append(rel)
            else:
                if not path.exists() or path.read_text(encoding="utf-8") != content:
                    changed.append(rel)
                atomic_write_text(path, content)
        if check and mismatched:
            raise SystemExit("render --check failed; mismatched files:\n" + "\n".join(mismatched))
        return changed if not check else mismatched


def _splice_generated(existing: str, rendered: str) -> str:
    """If template output is full file, use it; if existing has markers, replace block."""
    if GENERATED_START in rendered and GENERATED_END in rendered:
        # Prefer full rendered document from template
        return rendered
    start = existing.find(GENERATED_START)
    end = existing.find(GENERATED_END)
    if start == -1 or end == -1 or end < start:
        return rendered
    block_end = end + len(GENERATED_END)
    # Extract generated block from rendered if present
    rs = rendered.find(GENERATED_START)
    re_ = rendered.find(GENERATED_END)
    if rs != -1 and re_ != -1:
        new_block = rendered[rs : re_ + len(GENERATED_END)]
    else:
        new_block = GENERATED_START + "\n" + rendered + "\n" + GENERATED_END
    return existing[:start] + new_block + existing[block_end:]
