# Task 0 核验报告

核验时间：2026-09-19T13:05:00Z（本地 2026-09-19T21:05:00+0800）
执行者：Cursor Agent（本地实现，未推送远端）

## 1. 工作区与仓库

| 项 | 结果 |
|---|---|
| 初始 Cursor 工作区 | `/Volumes/T9/code/Jev`（空目录，非 Git 仓库） |
| 目标仓库 SSH | `git@github.com:fanly/Jev-awesome.git` |
| 克隆位置 | `/Volumes/T9/code/Jev-awesome`（独立目录，非嵌套其他项目） |
| 克隆结果 | 成功；warning: empty repository |
| 当前分支 | `main`（本地，尚无 commit） |
| `origin/main` | 不存在（远端无任何 ref） |
| 远端状态 | `gh repo view`：`isEmpty=true`，`diskUsage=0`，`defaultBranchRef.name=""` |
| 已有文件 | 仅 `.git/`，无 LICENSE/README/代码 |
| 未提交改动 | 无（空仓库） |
| Agent 根目录 | 已切换至 `/Volumes/T9/code/Jev-awesome` |

风险：空仓库没有可作为 PR base 的远端 main；首次上线需维护者 bootstrap 推送，不能假设现在就能开 PR。

## 2. 本机工具链

| 工具 | 版本 / 路径 |
|---|---|
| uv | 0.12.15（Homebrew） |
| 系统 python3 | 3.9.6（`/usr/bin/python3`，不适用） |
| Homebrew python | 3.14.7 |
| 选定解释器 | CPython 3.12.12（`uv python install 3.12`，符合文档默认） |
| gh | 已登录 `fanly`，scopes：`gist, read:org, repo` |
| TYPESAFE_API_KEY | 本环境未配置（不阻塞基础系统） |

## 3. TypeSafe / Jev 官方接口核验

| URL | 读取时间 (UTC) | 可访问 | 实际依据 |
|---|---|---|---|
| https://github.com/typesafe-ai/typesafe-sdk-python | 13:03 | 是 | 仓库页；README 确认 `uv add typesafe-sdk`、`TYPESAFE_API_KEY`、`TypeSafeClient.system_one`、`Choice`/`Noul`/`Score` |
| https://raw.githubusercontent.com/typesafe-ai/skills/.../SKILL.md | 13:03 | 是 | 完整技能指南；强调 live docs 为真相源；Noul 无独立 confidence |
| https://docs.typesafe.ai/llms.txt | 13:03 | 是 | 文档索引完整可读 |
| https://docs.typesafe.ai/sdk/python.md | 13:04 | 是 | 包名 `typesafe-sdk`；Async/Sync 客户端示例 |
| https://docs.typesafe.ai/sdk/python/api/constants.md | 13:04 | 是 | `API_KEY_ENV='TYPESAFE_API_KEY'`；`DEFAULT_BASE_URL='https://api.typesafe.ai'`；`DEFAULT_MODEL='jev-latest'` |
| https://docs.typesafe.ai/primitives.md | 13:04 | 是 | Choice/Score/Noul 字段；同请求问题互不可见 |
| https://docs.typesafe.ai/confidence.md | 13:04 | 是 | confidence 仅 Choice/Score；Noul 无 confidence |
| https://pypi.org/pypi/typesafe-sdk/json | 13:04 | 是 | **当前版本 0.7.0**，`requires_python>=3.10`，依赖 httpx2/pydantic/tenacity |
| https://pypi.org/pypi/typesafe/json | 13:04 | 是 | **无关包**（formal type asserting）；不可用 |
| https://pypi.org/pypi/typesafe-ai/json | 13:04 | 是 | 重定向 shim → `typesafe-sdk` |

结论：适配器必须用官方包 `typesafe-sdk`，读取 `TYPESAFE_API_KEY`，调用 `client.system_one(...)`。不得虚构 endpoint 或字段。Noul 只读 `.noul`，不得读不存在的 confidence。

## 4. GitHub 平台核验

| 能力 | 证据 |
|---|---|
| Search repositories | 匿名 `GET /search/repositories?q=topic:jev` → `total_count=351`，`incomplete_results=false` |
| 文档查询语法 | 五条查询均返回 200：`jev in:name,...`=7332；`"typesafe.ai" in:readme`=1414；`"@typesafe-ai/sdk"`=144；`"typesafe-sdk"`=264；`topic:jev`=351 |
| 匿名限流 | search limit=10/min；core=60/h。采集必须优先使用已有 `gh`/token，否则极易触顶 |
| Actions / PR / Pages | 文档入口已记录于 prompt [S7]–[S11]；本轮未推送、未启用 Actions |

## 5. 同类资源库比较（只作发现源参考，不搬运）

| 仓库 | Stars | 许可 | 观察 |
|---|---|---|---|
| hellogumbo/awesome-jev | 55 | CC0-1.0 | Node/`package.json` + `data/` + `site/`；社区目录定位 |
| yzfly/awesome-jev-zh | 5 | CC0-1.0 | 中文；`data/hot.json`/`projects.json`/`exclude.json`；宣称每日自动收录 |
| fatwang2/awesome-jev | 147 | MIT | `entries/` 分条目 + 可复用 GitHub review workflow；更偏证据 |
| Anil-matcha/awesome-jev-by-typesafe | 580 | MIT | use cases/patterns/prompts；偏官方用例集 |

本项目差异：机器观察与人工结论分层；未审核不进精选；无 Key 可跑；未合并 PR 候选保留；中文优先且解释 Jev 角色与证据边界。

## 6. 风险与阻塞

1. 远端空仓库：无 PR base，需 bootstrap 文档与命令。
2. 无 TYPESAFE_API_KEY：TypeSafe live 延后；Mock + rules 模式必须可跑。
3. 匿名 GitHub Search 配额极低：真实采集需用已登录 gh token（只读），不索要额外 PAT。
4. 搜索命中量大（数千）≠相关：必须规则过滤 + 人工审核，禁止自动 curated。
5. 未授权推送/合并/部署：本轮只本地实现与验证。

## 7. 已有实现

无。从空仓库全新建设。
