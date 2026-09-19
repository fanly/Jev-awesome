# AGENTS.md

## 项目目标

构建可维护的 Jev / TypeSafe 开发者参考库：发现 → 采集 → 去重 → 分类建议 → 人工精选 → 生成页面 → 定时更新。

## 硬规则

1. 无 `TYPESAFE_API_KEY` 时 `rules` 模式必须可运行。
2. TypeSafe 只用官方 `typesafe-sdk`，不虚构字段；Noul 无 confidence。
3. 采集不得直接 curated；不得覆盖人工摘要/审核/验证记录。
4. 未合并 PR 候选必须保留（merge-from 机器人分支数据）。
5. 默认测试离线；Mock 通过 ≠ live API 通过。
6. 未经用户明确授权：不推送、不合并、不改权限、不部署、不启用付费。

## 命令

见 README / `uv run jev-awesome --help`。
