from __future__ import annotations

import json
from pathlib import Path

from jev_awesome.atomic_io import atomic_write_text
from jev_awesome.models import EditorialStatus
from jev_awesome.paths import Paths
from jev_awesome.security import escape_md, safe_href
from jev_awesome.store import CatalogStore

SITE_CSS = """
:root {
  --bg: #f6f3ee;
  --ink: #1c1917;
  --muted: #57534e;
  --accent: #0f766e;
  --card: #fffdf9;
  --line: #d6d3d1;
  --font: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: var(--font);
  color: var(--ink);
  background:
    radial-gradient(1200px 600px at 10% -10%, #d9efe9 0%, transparent 55%),
    radial-gradient(900px 500px at 100% 0%, #f0e6d8 0%, transparent 50%),
    var(--bg);
  line-height: 1.55;
}
a { color: var(--accent); }
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {
  outline: 3px solid #f59e0b;
  outline-offset: 2px;
}
header, main, footer { width: min(920px, calc(100% - 2rem)); margin: 0 auto; }
header { padding: 2.5rem 0 1rem; }
h1 { font-size: clamp(1.8rem, 4vw, 2.6rem); margin: 0 0 0.4rem; letter-spacing: -0.02em; }
.tagline { color: var(--muted); margin: 0 0 1rem; }
.disclaimer { font-size: 0.95rem; color: var(--muted); }
.controls {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: 1fr;
  margin: 1.25rem 0 1.5rem;
  padding: 1rem;
  background: var(--card);
  border: 1px solid var(--line);
}
@media (min-width: 720px) {
  .controls { grid-template-columns: 2fr 1fr 1fr 1fr; align-items: end; }
}
label { display: grid; gap: 0.35rem; font-size: 0.9rem; color: var(--muted); }
input, select {
  font: inherit;
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
}
.list { display: grid; gap: 0.85rem; padding: 0 0 3rem; }
.item {
  padding: 1rem 1.1rem;
  background: var(--card);
  border-left: 4px solid var(--accent);
}
.item h2 { margin: 0 0 0.35rem; font-size: 1.15rem; }
.meta { color: var(--muted); font-size: 0.9rem; font-family: var(--mono); }
.empty { padding: 1.5rem; color: var(--muted); }
footer { padding: 1rem 0 2.5rem; color: var(--muted); font-size: 0.9rem; }
.badge { display: inline-block; margin-right: 0.4rem; font-size: 0.8rem; color: var(--muted); }
"""


def build_site(
    store: CatalogStore | None = None,
    paths: Paths | None = None,
    *,
    base_path: str = "/Jev-awesome/",
) -> Path:
    store = store or CatalogStore()
    paths = paths or store.paths
    out = paths.site_out
    out.mkdir(parents=True, exist_ok=True)

    curated = [
        r
        for r in store.list_resources(status_dir="resources")
        if r.editorial_status == EditorialStatus.CURATED
    ]
    proposed = [r for r in store.all_known() if r.editorial_status == EditorialStatus.PROPOSED]

    index = {
        "base_path": base_path if base_path.endswith("/") else base_path + "/",
        "resources": [_index_item(r, curated=True) for r in curated],
        "proposed_preview": [_index_item(r, curated=False) for r in proposed],
    }
    atomic_write_text(
        out / "search-index.json", json.dumps(index, ensure_ascii=False, indent=2) + "\n"
    )
    atomic_write_text(out / "styles.css", SITE_CSS)
    atomic_write_text(out / "app.js", _app_js(base_path))
    atomic_write_text(out / "index.html", _index_html(base_path, len(curated), len(proposed)))

    detail_dir = out / "r"
    detail_dir.mkdir(exist_ok=True)
    for r in curated + proposed:
        atomic_write_text(detail_dir / f"{_safe_id(r.id)}.html", _detail_html(r, base_path))

    return out


def _safe_id(rid: str) -> str:
    return rid.replace(":", "_").replace("/", "_")


def _index_item(r, *, curated: bool) -> dict:
    return {
        "id": r.id,
        "title": r.original_title,
        "summary_zh": r.summary_zh or "",
        "summary_en": r.summary_en or "",
        "tags": r.tags,
        "languages": r.languages,
        "category": r.primary_category.value if r.primary_category else "",
        "verification": r.verification_level.value,
        "url": safe_href(r.canonical_url) or "",
        "curated": curated,
        "detail": f"r/{_safe_id(r.id)}.html",
    }


def _index_html(base_path: str, n_curated: int, n_proposed: int) -> str:
    bp = base_path if base_path.endswith("/") else base_path + "/"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Jev-awesome</title>
  <link rel="stylesheet" href="{bp}styles.css"/>
</head>
<body>
  <header>
    <h1>Jev-awesome</h1>
    <p class="tagline">面向开发者的 Jev / TypeSafe 参考库：来源可追溯、人工精选。</p>
    <p class="disclaimer">非官方项目，与 TypeSafe 无隶属关系。精选 {n_curated} · 待审预览 {n_proposed}</p>
  </header>
  <main>
    <section class="controls" aria-label="过滤">
      <label>搜索<input id="q" type="search" placeholder="中文摘要 / 英文名 / 标签" autocomplete="off"/></label>
      <label>类别
        <select id="category">
          <option value="">全部</option>
          <option value="official">官方与变更</option>
          <option value="getting_started">入门与模式</option>
          <option value="applications">应用与工具</option>
          <option value="sdk_integrations">SDK 与集成</option>
          <option value="evals_limits">评测与限制</option>
          <option value="research_alts">研究与替代</option>
        </select>
      </label>
      <label>验证
        <select id="verification">
          <option value="">全部</option>
          <option value="discovered">discovered</option>
          <option value="source_checked">source_checked</option>
          <option value="code_located">code_located</option>
          <option value="reproduced">reproduced</option>
          <option value="benchmarked">benchmarked</option>
        </select>
      </label>
      <label>范围
        <select id="scope">
          <option value="curated">仅精选</option>
          <option value="proposed">待审预览</option>
          <option value="all">精选+待审</option>
        </select>
      </label>
    </section>
    <div id="results" class="list" aria-live="polite"></div>
  </main>
  <footer>
    <p>数据来自本仓库权威 JSON；拒绝队列不作为推荐展示。</p>
    <p><a href="https://github.com/fanly/Jev-awesome">GitHub</a></p>
  </footer>
  <script>window.JEV_BASE = {json.dumps(bp)};</script>
  <script src="{bp}app.js"></script>
</body>
</html>
"""


def _detail_html(r, base_path: str) -> str:
    bp = base_path if base_path.endswith("/") else base_path + "/"
    href = safe_href(r.canonical_url) or "#"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{escape_md(r.original_title)} · Jev-awesome</title>
  <link rel="stylesheet" href="{bp}styles.css"/>
</head>
<body>
  <header>
    <p><a href="{bp}index.html">← 返回</a></p>
    <h1>{escape_md(r.original_title)}</h1>
    <p class="meta">{escape_md(r.editorial_status.value)} · {escape_md(r.verification_level.value)}</p>
  </header>
  <main>
    <p><a href="{href}">{escape_md(href)}</a></p>
    <p>{escape_md(r.summary_zh or r.summary_en or "（暂无摘要）")}</p>
    <p><strong>Jev 角色：</strong>{escape_md(r.jev_role or "未填写")}</p>
    <p><strong>开发者价值：</strong>{escape_md(r.developer_value or "未填写")}</p>
    <p><strong>限制：</strong>{escape_md(r.limitations or "未填写")}</p>
  </main>
</body>
</html>
"""


def _app_js(base_path: str) -> str:
    _ = base_path
    return r"""
async function load() {
  const base = window.JEV_BASE || './';
  const res = await fetch(base + 'search-index.json');
  const data = await res.json();
  const root = document.getElementById('results');
  const q = document.getElementById('q');
  const category = document.getElementById('category');
  const verification = document.getElementById('verification');
  const scope = document.getElementById('scope');

  function items() {
    const curated = data.resources || [];
    const proposed = (data.proposed_preview || []).map(x => ({...x, preview: true}));
    if (scope.value === 'curated') return curated;
    if (scope.value === 'proposed') return proposed;
    return curated.concat(proposed);
  }

  function render() {
    const query = (q.value || '').trim().toLowerCase();
    const cat = category.value;
    const ver = verification.value;
    const filtered = items().filter(item => {
      if (cat && item.category !== cat) return false;
      if (ver && item.verification !== ver) return false;
      if (!query) return true;
      const blob = [item.title, item.summary_zh, item.summary_en, (item.tags||[]).join(' ')].join(' ').toLowerCase();
      return blob.includes(query);
    });
    if (!filtered.length) {
      root.innerHTML = '<div class="empty">没有匹配结果。试试清空筛选或更换关键词。</div>';
      return;
    }
    root.innerHTML = filtered.map(item => {
      const badge = item.preview || item.curated === false ? '<span class="badge">待审预览</span>' : '<span class="badge">精选</span>';
      return `<article class="item">
        <h2>${badge}<a href="${base}${item.detail}">${escapeHtml(item.title)}</a></h2>
        <p>${escapeHtml(item.summary_zh || item.summary_en || '')}</p>
        <p class="meta">${escapeHtml(item.verification)} · ${escapeHtml(item.category || 'uncategorized')}</p>
      </article>`;
    }).join('');
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  [q, category, verification, scope].forEach(el => el.addEventListener('input', render));
  render();
}
load();
"""
