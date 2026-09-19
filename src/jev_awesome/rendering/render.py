from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, select_autoescape

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.models import CATEGORY_META, EditorialStatus, PrimaryCategory, Resource
from jev_awesome.paths import Paths
from jev_awesome.security import escape_md, safe_href
from jev_awesome.store import CatalogStore

GENERATED_START = "<!-- JEV-AWESOME:GENERATED-START -->"
GENERATED_END = "<!-- JEV-AWESOME:GENERATED-END -->"


def _sort_key(r: Resource) -> tuple:
    return (
        0 if r.official_status.value == "official" else 1,
        (r.original_title or "").lower(),
        r.id,
    )


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
        return sorted(
            [
                r
                for r in self.store.list_resources(status_dir="resources")
                if r.editorial_status == EditorialStatus.CURATED
            ],
            key=_sort_key,
        )

    def proposed(self) -> list[Resource]:
        return sorted(
            [
                r
                for r in self.store.all_known()
                if r.editorial_status == EditorialStatus.PROPOSED
            ],
            key=_sort_key,
        )

    def render_all(self) -> dict[str, str]:
        curated = self.curated()
        proposed = self.proposed()
        counts = self.store.counts()
        by_cat: dict[PrimaryCategory, list[Resource]] = {c: [] for c in PrimaryCategory}
        for r in curated:
            if r.primary_category:
                by_cat[r.primary_category].append(r)

        ctx = {
            "curated": curated,
            "proposed": proposed,
            "counts": counts,
            "by_category": by_cat,
            "category_meta": CATEGORY_META,
            "generated_start": GENERATED_START,
            "generated_end": GENERATED_END,
            "safe_href": safe_href,
        }
        outputs: dict[str, str] = {}
        outputs["README.md"] = self.env.get_template("README.md.j2").render(**ctx)
        outputs["README.en.md"] = self.env.get_template("README.en.md.j2").render(**ctx)
        for cat, meta in CATEGORY_META.items():
            outputs[f"docs/categories/{meta['slug']}.md"] = self.env.get_template(
                "category.md.j2"
            ).render(category=cat, meta=meta, items=by_cat[cat], **ctx)
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
            raise SystemExit(
                "render --check failed; mismatched files:\n" + "\n".join(mismatched)
            )
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
