# 分阶段计划

## P0 — 核验与设计（本文件集）

- [x] 工作区/远端/空仓库确认
- [x] TypeSafe SDK 包名与常量核验
- [x] GitHub Search 查询语法实测
- [x] 同类库比较
- 交付：`task-0-audit.md` / `design.md` / `plan.md` / `progress.md`

## P1 — 模型、校验、去重、CLI、确定性生成

文件：

- `pyproject.toml`、`uv.lock`、`.python-version`
- `src/jev_awesome/models.py`、`normalize.py`、`dedupe.py`、`store.py`、`cli.py`
- `config/*.yaml`
- `templates/`、`src/jev_awesome/rendering/`
- `tests/` T01–T04、T09、T12、T18、T23、T29 相关子集

验收：`uv run pytest` 离线通过；`render` 两次无 diff；无 Key 可 `doctor`/`validate`。

## P2 — 采集适配器

- `sources/github.py`、`rss.py`、`official.py`、`http_safety.py`、`rate_limit.py`
- 真实只读小范围采集 → `data/inbox/` + run report
- 测试：T05–T08、T17、T27

## P3 — 审核与 TypeSafe

- `curation/review.py`、状态机迁移
- `classification/rules.py`、`classification/typesafe_adapter.py`
- Mock fixtures + 可选 live smoke（需授权与 Key）
- 测试：T09–T16、T23

## P4 — CI / 定时 / PR 状态机

- `.github/workflows/{ci,collect,pages}.yml`
- `automation/pr_state.py`、`scheduler.py`
- `docs/operations/{bootstrap,runbook}.md`
- 测试：T19–T22、T24–T26（fake GitHub）

## P5 — Seed 与静态站

- ≥30 真实候选（宁少勿假）、≥10 条中文摘要
- `docs/implementation/seed-review.md`
- `site/` 生成与子路径测试 T28

## P6 — 验收与交付

- 全量测试、秘密扫描、生成一致性
- `docs/implementation/final-report.md`
- 回复 `[JEV-AWESOME-BUILD-RESULT]`；不推送

## 命令契约（目标）

见 prompt §19；实现后以 `uv run jev-awesome --help` 为准。
