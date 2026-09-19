# R1 验收矩阵 T01–T30

生成：2026-09-19（对照源码工作区；测试命令见 verification-report）  
规则：不以“测试总数”替代逐项映射；一测可盖多项，但须有具体断言。

| 原验收 ID | 要求（摘要） | 实现文件/符号 | 测试 nodeid | 经生产入口 | 本轮结果 | 证据 |
|---|---|---|---|---|---|---|
| T01 | 相同数据连续生成两次无 diff | `rendering/render.py`；`collect.run_collect` | `tests/test_core.py`（render 幂等）；`tests/test_coverage_checkpoint.py::test_t01_fixture_collect_idempotent_dispositions` | render CLI / collect | PASS | pytest |
| T02 | 同仓库 URL/大小写/改名合并 | `normalize.py` / store merge | `tests/test_core.py` | 是（store） | PASS | pytest |
| T03 | 不同 owner 同名不合并 | `normalize.py` | `tests/test_core.py` | 是 | PASS | pytest |
| T04 | 模糊/非法日期不填今天 | `dates.py` | `tests/test_dates.py` | 是 | PASS | pytest |
| T05 | 多页/不完整搜索 → coverage | `sources/github.py` QueryCoverage；`models.SourceResult.coverage_status` | `tests/test_coverage_checkpoint.py::test_t05_*`；`tests/test_github_http.py` | adapter | PASS | page_budget→partial；short page→complete |
| T06 | 401/403/429/5xx 分类 | `sources/github.py` / http_client | `tests/test_github_http.py::test_t06_401_no_blind_retry` | adapter | PASS | pytest |
| T07 | 单源失败不删目录 | `automation/collect.py` | `tests/test_automation_review.py` / collect degraded | collect | PASS | 报告 overall=degraded 路径存在 |
| T08 | ETag 304 复用 | official/rss adapters | 有限；官方 monitor ETag 逻辑在源码 | 部分 | PARTIAL | 实现存在；专用断言偏薄 |
| T09 | 人工摘要 vs 机器建议 | `write_policy.filter_machine_resource_update`；`merge_machine_fields` | `tests/integration/test_publisher_rounds.py::test_t09_field_policy_preserves_editorial` | publisher 再校验 | PASS | 人工字段保留；status 跃迁拒绝 |
| T10 | 已拒绝再发现不入队 | store decisions + collect disposition | `tests/test_site.py::test_t10_rejected_same_hash_decision`；collect `suppressed_rejected` | collect | PASS | pytest |
| T11 | claimed reproduced 无证据失败 | models / validate | `tests/test_core.py` / validate | validate | PASS | schema |
| T12 | 无 Key rules 全流程 | `RulesClassifier`；CLI | `tests/test_classifier_security.py::test_t12_rules_mode_zero_model_calls` | CLI | PASS | doctor 显示 KEY absent |
| T13 | typesafe 缺 Key 明确失败 | `TypeSafeClassifier` | `tests/test_classifier_security.py::test_t13_typesafe_strict_missing_key` | 分类器 | PASS | pytest |
| T14 | TypeSafe 异常保留候选 | `TypeSafeClassifier` | `tests/test_classifier_security.py::test_t14_typesafe_error_keeps_candidate_path` | 分类器 | PASS | Mock |
| T15 | Noul 无 confidence | typesafe_adapter | `tests/test_classifier_security.py::test_t15_noul_has_no_confidence_read` | 分类器 | PASS | Mock |
| T16 | 提示注入不改审核状态 | `RulesClassifier` + `apply_suggestion_fields` | `tests/test_classifier_security.py::test_t16_prompt_injection_ignored` | 分类器 | PASS | pytest |
| T17 | 非法 URL/内网/fake-ip | `security.validate_url_for_fetch` | `tests/test_classifier_security.py::test_t17*` | HTTP 出口 | PASS | 默认拒 198.18；`JEV_ALLOW_FAKE_IP=1` 本地例外；CI 强制关 |
| T18 | MD/HTML 注入转义 | `security.escape_md` / site | `tests/test_classifier_security.py::test_t18_markdown_escape` | render/site | PASS | pytest |
| T19 | 三轮未合并 PR 保留候选 | `Publisher` + bare Git + `FakeGitHubTransport` | `tests/integration/test_publisher_rounds.py::test_t19_three_rounds_unmerged_retain_candidates` | **生产 Publisher** | PASS | A→A+B→A+B+C；单开放 PR；round4 无 POST/PATCH |
| T20 | 人工改机器人分支暂停 | `Publisher` + `manual_edits_suspected` | `tests/integration/...::test_t20_manual_remote_divergence_pauses` | Publisher | PASS | pending-robot-write.json |
| T21 | 合并/关闭/并发策略 | `_ensure_pr` closed-unmerged | `tests/integration/...::test_t21_closed_unmerged_pr_does_not_auto_reopen` | Publisher | PASS（关闭未合并）；合并后续/分支删除恢复仍为 PARTIAL | pytest |
| T22 | dry-run / disabled 无写 | `Publisher.publish` + workflow | `tests/integration/...::test_t22_disabled_and_dry_run_no_writes`；`tests/test_workflow_gates.py` | Publisher + YAML | PASS | transport.calls==[]；YAML 需 auto_pr+非 dry |
| T23 | 采纳/拒绝/归档 | `curation/review.py` | `tests/test_automation_review.py::test_t23_approve_reject_flow` | review CLI | PASS | fixture 临时库 |
| T24 | 纯检查时间不空提交 | Publisher `no_diff` | T19 round4 | Publisher | PASS | 无 write API |
| T25 | UTC cron ↔ UTC+8 | doctor schedule 表；workflow cron | doctor 输出 | 文档/CLI | PASS | doctor 列出映射 |
| T26 | 周报边界 | `docs/updates` + weekly 逻辑 | 有周报文件；重跑断言有限 | 部分 | PARTIAL | 未扩测 |
| T27 | 缓存丢失/失败分片不推进检查点 | `CheckpointStore` | `tests/test_coverage_checkpoint.py::test_t27_failed_shard_does_not_advance_checkpoint` | collect | PASS | dry_run/durable=False 不写 |
| T28 | Pages 子路径 | `site/build.py` base_path | `tests/test_site.py::test_t28_site_base_path_and_index` | site build | PASS | `/Jev-awesome/`；本地构建≠部署 |
| T29 | 未审核不进精选 | render curated filter | `tests/test_core.py` / site | render | PASS | curated=0 |
| T30 | 假 reviewer / 越权路径 | `reject_malicious_artifact_paths`；字段策略 | `tests/integration/...::test_t30_malicious_artifact_paths_rejected`；T09 | Publisher | PASS | 拒 `../`、源码、workflow |

## 汇总

- **PASS**：T01–T07、T09–T20、T22–T25、T27–T30（及 T21 关闭未合并场景）
- **PARTIAL**：T08（ETag 断言偏薄）、T21（合并后继续 / 分支删除恢复未全覆盖）、T26（周报重跑）
- **不以 47 passed 宣称 30/30**：见上表 PARTIAL 项

## Workflow 门控（可执行）

`tests/test_workflow_gates.py`：publish 非占位；permissions 分 job；`dry_run==false` ∧ `auto_pr==true`；CI 强制 `JEV_ALLOW_FAKE_IP=0`。
