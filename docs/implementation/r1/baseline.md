# R1 Task 0 基线冻结

冻结时间：2026-09-19T14:00:32Z  
核查路径：`/Volumes/T9/code/Jev-awesome`  
本文件记录核查时的源码身份；后续提交会改变 HEAD，不以本文件自哈希为准。

## 1. 仓库身份

| 项 | 实测值 |
|---|---|
| Git 根 | `/Volumes/T9/code/Jev-awesome` |
| remote origin | `git@github.com:fanly/Jev-awesome.git` |
| 分支 | `main`（upstream 指向已消失的 origin/main） |
| HEAD（冻结） | `7634255ec6fc40f7057d82cd97e11be864755ede` |
| 工作区 | clean（无未提交改动） |
| `git ls-remote origin` | 空（无 refs） |
| `gh repo view isEmpty` | `true`，`defaultBranchRef.name=""` |
| uv.lock SHA-256 | `7481c62a2eeb1b6bb459006880dc401b66c6e27aa7d8b19ef08bd35555f9d632` |
| pyproject.toml SHA-256 | `8dd9f44368de28fd5147731caa578f5687e5001f45d7925c4e7afa838a4e4506` |
| typesafe-sdk | `0.7.0`（已安装） |
| inbox | 131 文件；proposed≈34，pending≈97；curated=0 |

## 2. 生产入口（现状）

| 能力 | 路径 | 状态 |
|---|---|---|
| CLI | `src/jev_awesome/cli.py` → `jev-awesome` | 可用 |
| 采集 | `automation/collect.py` + `sources/*` | 可用；覆盖语义不完整 |
| 审核 | `curation/review.py` | 可用 |
| 生成 | `rendering/render.py` / `site/build.py` | 可用 |
| Publisher | **缺失**；workflow `publish-pr` 仅 echo + `exit 0` | **占位** |
| PR 状态 | `automation/pr_state.py` FakeGitHub / merge_inbox_rounds | **仅字典/状态机，非生产路径** |
| Workflow | `.github/workflows/collect.yml` | 门控基本有；发布未接线 |

## 3. 上次“完成” vs 实际

| 声明 | 核实 |
|---|---|
| P4 完成（远端未启用） | **过度声明**。应改为「部分实现」：定时/门控 YAML 存在，但 publish-pr 为占位；三轮未合并持久化未走生产 publisher |
| P6 完成 | 仅本地命令抽检；**不能**替代 T01–T30 完整映射 |
| fake-ip 仅 allowlist 容忍 | 实现为：allowlist 域名解析到 `198.18/15` **默认放行**，缺少「显式本地开关 / CI 禁止」隔离 |
| 「等维护者确认路径策略」阻塞 publish | **不成立**。R1 Prompt 已给出最小写入边界；属本地未实现，非账户阻塞 |
| 32 tests = 验收通过 | **不成立**。缺 T19–T22 生产路径、T05 覆盖状态、T17 默认拒 fake-ip、T27 检查点、T30 artifact 越权等 |

## 4. 三类缺口

### 真实缺失（本轮必须补）

1. 生产 publisher（路径+字段双层校验、Git transport、PR API、无 diff 不写）
2. 经 publisher 的三轮未合并 PR 集成测试（临时 bare Git + fake HTTP）
3. 查询级 coverage_status（complete/partial/unknown）与 page_budget 缺口
4. 计数对账 / disposition 记录
5. 增量检查点（成功可恢复保存后才推进；dry-run 不推进）
6. fake-ip：默认/CI 严格拒绝；仅 `JEV_ALLOW_FAKE_IP=1` 本地例外
7. T01–T30 验收矩阵与证据

### 已有但未充分验证

- merge_from 机器人分支数据合并（有代码，缺 publisher 端到端）
- 人工字段保护 `merge_machine_fields`（有单测，缺发布路径再校验）
- Workflow 门控字符串比较（需可执行验证，不只文档）

### 仅外部未启用（本轮不执行）

- 推送 origin / 真实 PR / schedule / Pages / TypeSafe live / 维护者采纳 curated

## 5. 本轮拟改文件（理由）

| 文件 | 理由 |
|---|---|
| `src/jev_awesome/automation/write_policy.py` | 路径与字段白/黑名单 |
| `src/jev_awesome/automation/github_transport.py` | 真实 HTTP transport + 可注入 fake |
| `src/jev_awesome/automation/git_workspace.py` | 临时/工作区 Git 操作（不碰真实 origin 身份） |
| `src/jev_awesome/automation/publisher.py` | 生产发布编排 |
| `src/jev_awesome/automation/coverage.py` / models SourceResult 扩展 | 覆盖与对账 |
| `src/jev_awesome/automation/checkpoint.py` | 增量检查点 |
| `src/jev_awesome/security.py` | fake-ip 默认关闭 |
| `src/jev_awesome/sources/github.py` + collect.py | 覆盖报告、disposition、检查点 |
| `src/jev_awesome/cli.py` | `publish` 子命令 |
| `.github/workflows/collect.yml` | 接线真实 publish；删占位 echo |
| `config/runtime.yaml` / write_policy 常量 | 开关与策略 |
| `tests/integration/test_publisher_rounds.py` 等 | R1-B 场景 |
| `docs/implementation/r1/*` | 基线、矩阵、验证报告 |
| `docs/operations/bootstrap.md` | Gate 1–5 与真实命令 |
| `docs/implementation/seed-review.md` | 抽查更新（不改审核状态） |

不重写：已充分的 models、review CLI、render 幂等、rules 分类器核心逻辑。

---

## 6. R1 补齐后快照（相对冻结点）

实现完成后工作区含未提交/将提交的 publisher、write_policy、transport、checkpoint、integration tests 与 r1 文档。  
以 `verification-report.md` 与本地提交 SHA 为准；本基线冻结 HEAD 仍为上表 `7634255…`。
