# Bootstrap（空远端 → 首次上线）

核验时间基线：远端曾为完全空仓库（无 commit / 无 `origin/main`）。**推送前请再次确认远端状态。**

## 1. 本地审阅

```bash
cd /Volumes/T9/code/Jev-awesome
uv sync --frozen
uv run pytest
uv run jev-awesome validate
uv run jev-awesome render --check
uv run jev-awesome doctor
# 审阅 docs/implementation/seed-review.md
```

## 2. 首次推送（需维护者明确授权后执行）

再次检查远端是否仍为空：

```bash
git ls-remote origin
gh repo view fanly/Jev-awesome --json isEmpty,defaultBranchRef
```

若仍为空，在审阅本地历史后：

```bash
git push -u origin main
```

若远端已有提交：先 `git fetch` 并对齐，**不要 force push**。

## 3. Actions 权限

- 仓库 Settings → Actions → General：允许 Actions；需要自动 PR 时开启 “Allow GitHub Actions to create and approve pull requests”。
- Workflow 内已按 job 授予最小权限；保持默认 token 克制。

## 4. 仓库变量 / Secrets

Repository Variables：

```text
COLLECTOR_ENABLED=false
AUTO_PR_ENABLED=false
PAGES_ENABLED=false
```

Secrets（可选）：

```text
TYPESAFE_API_KEY=
```

`GITHUB_TOKEN` 由平台注入，勿写入公开文件。

## 5. 首次 dry-run

```text
Actions → Collect → Run workflow
dry_run=true, mode=incremental, classifier=rules
```

检查日志、coverage gaps、artifact `collect-report`。

## 6. 写入模式（再次明确授权）

将 `COLLECTOR_ENABLED=true`，workflow_dispatch 且 `dry_run=false`。确认后再设 `AUTO_PR_ENABLED=true`。

## 7. 采纳 seed

使用真实 GitHub 登录名作为 `--reviewer`（仅审计字段）：

```bash
uv run jev-awesome review list
uv run jev-awesome review approve <ID> --reviewer YOUR_LOGIN
uv run jev-awesome render
```

## 8–10. 定时 / TypeSafe / Pages

按需开启；默认保持 rules、Pages 关闭。启用 Pages 后检查实际 `page_url` 与 `/Jev-awesome/` 子路径。
