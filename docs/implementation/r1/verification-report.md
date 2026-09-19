# R1 验证报告

生成时间：2026-09-19（本地）  
对照基线：`docs/implementation/r1/baseline.md`（冻结 HEAD `7634255ec6fc40f7057d82cd97e11be864755ede`）  
本报告提交后 HEAD 会变化；以本文件内命令结果与验收矩阵为准，不作自引用哈希。

## 1. 原报告修正

| 项 | 原声明 | R1 核实后 |
|---|---|---|
| P4 | 「完成（远端未启用）」 | **曾为部分实现（publish-pr 占位）**；本轮已补生产 `Publisher` + workflow 接线；远端写入仍默认关 |
| P6 / 32 tests | 等同验收完成 | **不成立**；见 acceptance-matrix；现 pytest **47 passed** 仍含 PARTIAL 项 |
| fake-ip | allowlist 即安全 | **默认/CI 拒绝**；仅 `JEV_ALLOW_FAKE_IP=1` 且非 CI |
| 「等路径策略」 | 阻塞 publish | **本地未实现，非账户阻塞**（已实现 write_policy） |

## 2. 命令结果（本轮实测）

| 命令 | 退出码 | 结果 |
|---|---|---|
| `uv sync --frozen` | 0 | 40 packages |
| `uv run jev-awesome doctor` | 0 | rules；三开关 false；`JEV_ALLOW_FAKE_IP=off(default)` |
| `uv run jev-awesome validate` | 0 | curated=0 proposed=34 pending=97 inbox=131 |
| `uv run jev-awesome render --check` | 0 | ok |
| `uv run jev-awesome site build` | 0 | → `site/dist`（本地构建，非部署） |
| `uv run pytest` | 0 | **47 passed** |
| `uv run ruff check`（R1 改动路径） | 0 | All checks passed |
| `uv run ruff format --check .` | ≠0 | 仓库内仍有**既有**未格式化文件；R1 改动文件已 format |
| `uv run basedpyright`（publisher/security 等） | 0 | 0 errors |
| 秘密模式扫描（ghp_/github_pat_/sk-/AKIA） | 0 命中 | 工作区+跟踪文件模式扫描；无全文输出 |

未执行：真实 `git push`、真实 PR、schedule 启用、Pages 部署、TypeSafe live、正式 `review approve`。

## 3. Publisher / 三轮 PR

生产入口：`jev-awesome publish` → `automation/publisher.py`  
Transport：`HttpxGitHubTransport`（生产）/ `FakeGitHubTransport`（测试）  
Git：临时 bare remote（测试永不替换真实 origin 身份）

集成证据（`test_t19`）：

1. Round1：仅 A → `pr_created` #1  
2. Round2：合并机器人数据后加 B → `pr_updated` #1；机器人树含 A+B；`first_discovered_at(A)` 不变  
3. Round3：加 C → 仍 1 个开放 PR；含 A+B+C  
4. Round4：无变化 → 无 POST/PATCH  

另：`test_t20` 人工 tip → `paused`；`test_t21` 关闭未合并 → 不自动重开；`test_t22` disabled/dry_run 零 API 写。

策略：在**可信上一轮 robot tip** 上快进提交（禁止 force push）。

## 4. 采集覆盖与检查点

- `coverage_status`: complete | partial | unknown  
- `gap_reason`: 含 `page_budget` / `incomplete_results` 等  
- `max_pages=1` 且仍有下一页 → **partial**（非 complete）  
- `CheckpointStore`：仅 `durable=True` 且非 dry-run 推进  

上次真实采集（历史）：discovered 量与 inbox=131 的精确对账日志不足 → **「上次无法精确回溯」**。本轮 validate：pending=97 + proposed=34 = 131；curated=0。

## 5. 安全

- 路径 allowlist + 字段黑名单（摘要/审核/验证等级等）  
- Artifact 拒 `..`、源码、workflow  
- 网络：默认拒 fake-ip；workflow 设 `CI=true` + `JEV_ALLOW_FAKE_IP=0`  
- 信任边界：本地代理最终目的 IP 客户端无法独立证明时，文档不虚报

## 6. 内容

- curated=0；未伪造 fanly 批准  
- Seed 抽查见更新后的 `seed-review.md`（建议≠采纳）  
- 首页/精选统计不含 pending

## 7. TypeSafe

Mock/离线接口验证通过；**live 未验证**。

## 8. 远端

未推送；未开真实 PR；COLLECTOR/AUTO_PR/PAGES 均为 false。

## 9. 建议状态

**LOCAL_READY_FOR_BOOTSTRAP**（本地关键路径与证据齐备；非生产上线通过）

残余 PARTIAL：T08/T26/T21 部分恢复场景——不阻塞首次推送审阅，但合并后持续运行前建议补测。
