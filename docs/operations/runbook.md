# 运维手册

## 日常命令

```bash
uv run jev-awesome doctor
uv run jev-awesome collect --mode incremental --classifier rules --dry-run
uv run jev-awesome collect --mode incremental --classifier rules --write-local
uv run jev-awesome review list
uv run jev-awesome render --check
uv run jev-awesome weekly --previous-complete-week
uv run jev-awesome site build
```

## 权限分离

| 能力 | 开关 |
|---|---|
| 写本地 catalog | `--write-local` |
| 写远端 / PR | `AUTO_PR_ENABLED` + publish job |
| 调用模型 | `--classifier typesafe|auto` + `TYPESAFE_API_KEY` |
| 部署站点 | `PAGES_ENABLED` |

## 未合并机器人 PR

下一轮采集必须 `--merge-from` 未合并分支工作树（workflow 已实现），避免从 main 重建丢候选。

## 健康与补跑

- 定时可能延迟或漏跑；用 workflow_dispatch 补跑。
- `data/reports/latest.json` 区分 success / degraded / failed。
- Fork 中默认不跑写入（`github.repository == fanly/Jev-awesome`）。
