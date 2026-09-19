# Bootstrap（R1 更新）

对照：`docs/implementation/r1/verification-report.md`。  
**本文件只准备步骤；Gate 2–5 本轮不执行。**

## Gate 1：本地可启动（本轮目标）

已具备：生产 `Publisher`（默认关闭远端写）、路径/字段策略、三轮未合并集成测试、coverage/checkpoint、fake-ip 默认关、47 pytest、validate/render/site 本地通过。

```bash
cd /Volumes/T9/code/Jev-awesome
uv sync --frozen
uv run pytest
uv run jev-awesome validate
uv run jev-awesome render --check
uv run jev-awesome doctor
uv run jev-awesome site build   # → site/dist，不是部署
# 审阅 docs/implementation/seed-review.md 与 r1/acceptance-matrix.md
```

确认变量语义（字符串 `true` 才启用）：

```text
COLLECTOR_ENABLED=false
AUTO_PR_ENABLED=false
PAGES_ENABLED=false
```

本地 Clash fake-ip 仅在明确设置 `JEV_ALLOW_FAKE_IP=1` 且非 CI 时允许 allowlist 域名；**不要**在 CI/发布环境打开。

## Gate 2：首次推送（未执行）

```bash
git ls-remote origin
gh repo view fanly/Jev-awesome --json isEmpty,defaultBranchRef
# 若仍为空且审阅通过：
# git push -u origin HEAD:main
# 若远端已有提交：fetch 对齐，禁止 force push
```

推送前再核验当前分支名与完整 SHA（勿盲推旧说明）。

## Gate 3：远端 dry-run（未执行）

Actions → Collect → `dry_run=true`，classifier=rules。  
检查 job summary、coverage、artifact `collect-report`。schedule 与 Pages 仍关。

## Gate 4：一次真实机器人 PR（未执行）

独立授权后：workflow_dispatch 且 `dry_run=false`，再设 `AUTO_PR_ENABLED=true`。  
运行 `jev-awesome publish` 路径（workflow `publish-pr` job）。  
可保持 `COLLECTOR_ENABLED=false` 避免定时并发。

## Gate 5：内容采纳与持续运行（未执行）

```bash
uv run jev-awesome review show <ID>
uv run jev-awesome review approve <ID> --reviewer <YOUR_GITHUB_LOGIN>
uv run jev-awesome render
```

`--reviewer` 仅为审计字符串，**不是授权证明**。  
schedule / Pages / TypeSafe live **分别**授权，不捆绑。

## 发布 CLI（本地 dry 默认）

```bash
# 默认跳过远端
uv run jev-awesome publish
# 显式启用仍受 dry-run / token 约束；勿对真实 origin 试验除非 Gate 4 授权
```
