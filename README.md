# Jev Awesome

**把 Jev 用在正确的决策点上。**

面向开发者的 **Jev / TypeSafe** 精选：说明每个项目里 Jev 负责哪一步、先读哪段源码、需要什么依赖，以及哪些结论还没有运行验证。

中文 · [English](README.en.md)

先理解边界，再选一个入口动手：官方 SDK、浏览器与移动 Agent、数据库语义判断、本地研究实现，以及能看清方法的独立评测。

[从这里开始](docs/guides/start-here.md) · [按场景选项目](docs/guides/choose-your-path.md) · [浏览器决策源码导读](docs/guides/browser-agent-code-tour.md)

<!-- JEV-AWESOME:GENERATED-START -->
## 我想解决什么问题？

| 场景 | 建议先看 | 为什么 |
|---|---|---|
| 在 Python/TS 里接入类型化判断 | [Python SDK](https://github.com/typesafe-ai/typesafe-sdk-python) / [JS SDK](https://github.com/typesafe-ai/typesafe-sdk-js) | 官方客户端，问题与返回类型清晰 |
| 浏览器 Agent：选动作 vs 写文字 | [Jev Ultrafast](https://github.com/browser-use/jev-ultrafast) | 可读的决策循环，动作空间与文本生成分工明确 |
| Android 观察→决策→执行 | [Mobile Jev](https://github.com/droidrun/mobile-jev) | 设备侧 Agent 链路与 studio/CLI 分工 |
| 在 SQL/图库里做语义分流 | [pg-jev](https://github.com/realZachi/pg-jev) / [neo4jev](https://github.com/jexp/neo4jev) | 把候选行/边交给 Choice，而不是用自由文本糊弄查询 |
| 本地或研究替代实现 | [LocalJev](https://github.com/githubnext/localjev) / [kev](https://github.com/jaredpalmer/kev) | 分清「兼容桥接」与「独立训练」 |
| 对照延迟/成本/判断质量 | [typesafe-ai-benchmark](https://github.com/iammrduncan/typesafe-ai-benchmark) | 同一任务下多路径对照，保留原始结果与方法 |

## 首批编辑精选


### [typesafe-ai/typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python)
官方 Python SDK（PyPI: typesafe-sdk）。用 `TypeSafeClient.system_one` 提交 Choice / Noul / Score，拿到概率化结构化判断，而不是自由生成文本。

- **Jev 角色：** 对 state 上的 typed questions 返回 choice/noul/score 与概率；不负责写散文。
- **开发价值：** 把「在候选中做校准判断」接到任意 Python 服务；是接入官方 Jev 的默认客户端。
- **限制：** 无 Key 无法调真实 Jev；Mock/Adapter 结果≠官方模型。本目录未做 live 复现。
- **验证：** `source_checked` · 身份 `official` / `official`

### [typesafe-ai/typesafe-sdk-js](https://github.com/typesafe-ai/typesafe-sdk-js)
官方 TypeScript/JavaScript SDK，与 Python 客户端同属 System One 调用面。

- **Jev 角色：** 官方客户端：system_one + Choice/Noul/Score；不替代业务编排。
- **开发价值：** 在 Node / 浏览器后端侧接入同一套 typed questions，与 Python 团队对齐契约。
- **限制：** 需有效 Key；本目录仅 source_checked，未跑通线上调用。
- **验证：** `source_checked` · 身份 `official` / `official`

### [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast)
Browser Use × TypeSafe：动态编号动作空间；Jev 选 operation/target，仅 TYPE_TEXT 时才让小 LLM 写字。

- **Jev 角色：** 一次请求内选出 CLICK/TYPE_TEXT/… 与目标元素索引；不生成页面文案。
- **开发价值：** 学习「决策与文本生成解耦」的可运行浏览器 Agent；先读 agent 循环比抄提示词更有用。
- **限制：** 演示延迟/路径依赖真实页面与 Key；本目录未复现其 7.1s 声明。云端 waitlist 与本地 demo 是不同产品面。
- **验证：** `code_located` · 身份 `community` / `calls_official_api`

### [droidrun/mobile-jev](https://github.com/droidrun/mobile-jev)
Android 真机 Agent：Mobilerun 观察/执行，Jev 做决策；含 React studio、CLI 与痕迹。

- **Jev 角色：** 根据屏幕观察在动作候选中做结构化选择；不直接驱动触摸硬件。
- **开发价值：** 看清手机侧「观察→Jev 决策→执行」链路与本地 studio，而不是又一个聊天 demo。
- **限制：** 设备/云服务单独计费；完整订票类 demo 未演示成交。本目录未接真机复现。
- **验证：** `source_checked` · 身份 `community` / `calls_official_api`

### [realZachi/pg-jev](https://github.com/realZachi/pg-jev)
PostgreSQL 扩展：用自然语言条件过滤/排序/分类行；每行由 Jev 判概率，无向量列。

- **Jev 角色：** 对行级条件返回概率（jev / jev_prob）；不负责生成 SQL 或嵌入。
- **开发价值：** 把「语义过滤」放进 SQL，而不是在应用层把整表塞进聊天模型。
- **限制：** 每行/批调用有成本与延迟；许可为 PostgreSQL 类（NOASSERTION 元数据）。本目录未装扩展复现。
- **验证：** `source_checked` · 身份 `community` / `calls_official_api`

### [jexp/neo4jev](https://github.com/jexp/neo4jev)
Neo4j 图导航演示：每跳把出边做成 Choice，并同请求问 Noul「是否到达目标」。

- **Jev 角色：** 单跳 Choice（跟哪条边）+ Noul（是否到达）；应用层做 beam 与可视化。
- **开发价值：** 学习如何用概率路径/beam search 做图遍历，而不是让 LLM 编造下一跳。
- **限制：** 演示图与自建图 schema 不同；本目录未连接 Neo4j/live Jev。
- **验证：** `code_located` · 身份 `community` / `calls_official_api`

### [githubnext/localjev](https://github.com/githubnext/localjev)
GitHub Next：本地兼容 `POST /v1/systemone` 的实现（Bun + Diffusion），用于研究/桥接。

- **Jev 角色：** 本地兼容端点；不是官方托管 Jev，质量与校准不可直接等同。
- **开发价值：** 在无官方 Key 或要本地试验时，对齐 System One 契约做客户端联调。
- **限制：** 名称易与官方混淆；输出≠官方 Jev。本目录未本地启动服务。
- **验证：** `source_checked` · 身份 `community` / `inspired_independent`

### [jaredpalmer/kev](https://github.com/jaredpalmer/kev)
受 Jev 启发的可训练小型决策模型（Qwen + LoRA/读出头）；提供兼容 System One 的服务端。

- **Jev 角色：** 独立模型族；API 形状对齐 System One，但权重与校准是作者自己的。
- **开发价值：** 研究「概率读出 vs 解码文本」、本地训练与冻结评测套件；可换 base_url 试官方 SDK。
- **限制：** 作者自述部分 checkpoint 未过其发布门槛；数字不可当官方 Jev 成绩。本目录未训练/未服务。
- **验证：** `source_checked` · 身份 `community` / `inspired_independent`

### [typesafe-ai/skills](https://github.com/typesafe-ai/skills)
官方 Agent Skill：教代理如何用 System One / Jev 设计类型化工作流。

- **Jev 角色：** 技能文档与提示；不本身调用模型（由宿主代理决定是否调 API）。
- **开发价值：** 在 Claude Code / skills.sh 里快速对齐「该问 Choice 还是 Noul」的设计习惯。
- **限制：** 安装技能≠已配置 API Key；本目录未验证各宿主安装路径。
- **验证：** `source_checked` · 身份 `official` / `official`

### [iammrduncan/typesafe-ai-benchmark](https://github.com/iammrduncan/typesafe-ai-benchmark)
并排对照：Cerebras 上 Qwen 结构化输出 vs TypeSafe Jev vs 本地 Needle，记录延迟、成本与校验通过情况。

- **Jev 角色：** 基准中的原生判断路径；与 LLM schema 输出、本地 tool-call 对照。
- **开发价值：** 读方法与原始导出，判断「换模型」还是「换决策形态」；不要只看首页 GIF。
- **限制：** 作者自述 Needle 测量条件不同，不能当严格速度排名。本目录仅阅读公开方法与结果页，未重跑基准 → verification 非 benchmarked。
- **验证：** `source_checked` · 身份 `community` / `calls_official_api`




## 动手：官方 Python SDK

最小可运行示例以官方仓库为准（`TypeSafeClient.system_one` + `Choice` / `Noul` / `Score`），需要 `TYPESAFE_API_KEY`：

- 源码与 Quickstart：[typesafe-ai/typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python)
- 文档：[docs.typesafe.ai/sdk/python](https://docs.typesafe.ai/sdk/python/)

本目录不提供本地半成品 / mock 脚本。

## 不止收链接：三篇中文导读

1. [Jev 到底适合放在你的程序哪一步？](docs/guides/start-here.md)
2. [官方 API、社区 SDK、LocalJev、kev：应该从哪里开始？](docs/guides/choose-your-path.md)
3. [读 Jev Ultrafast：为什么「选动作」和「写文字」要分开？](docs/guides/browser-agent-code-tour.md)

## 完整分类（仅计精选）

- [官方与变更](docs/categories/official.md)（2）
- [入门与模式](docs/categories/getting-started.md)（2）
- [应用与工具](docs/categories/applications.md)（4）
- [SDK 与集成](docs/categories/sdk-integrations.md)（3）
- [评测与限制](docs/categories/evals-limits.md)（1）
- [研究与替代实现](docs/categories/research-alts.md)（2）


当前精选 **14** 条；待审队列另有 118 条（不计入上方推荐）。

## 最近编辑更新

- **2026-09-20 · launch-v1**：首批编辑精选与三篇中文导读发布（代理编辑身份 `cursor:delegated-editor`；未进行真人逐条复核或第三方运行复现）。详见 [docs/launch/launch-v1-batch.md](docs/launch/launch-v1-batch.md)。

## 如何读验证标记

| 级别 | 含义 |
|---|---|
| discovered | 有线索，未确认实现 |
| source_checked | 阅读了原始资料 |
| code_located | 定位到实现位置 |
| reproduced | 有可复核的运行证据 |
| benchmarked | 有基线与口径的对照评测 |

精选表示「本目录编辑入选」，**不等于**本仓库已运行复现。自动化不得自行抬高 `reproduced` / `benchmarked`。
<!-- JEV-AWESOME:GENERATED-END -->

## 更多生态导航（非首批核心）

其他 Awesome 清单适合扫目录，**不替代**上面的精选卡片：

- [awesome-jev](https://github.com/hellogumbo/awesome-jev)
- [awesome-jev-zh](https://github.com/yzfly/awesome-jev-zh)
- [awesome-jev-projects](https://github.com/logicrw/awesome-jev-projects)

## 贡献与仓库维护

贡献与纠错见 [CONTRIBUTING.md](CONTRIBUTING.md)。维护本仓库本身（采集器、校验、render）见 [docs/operations/bootstrap.md](docs/operations/bootstrap.md)。

> 非官方项目，与 TypeSafe 无隶属关系。资料可能过时，请自行评估上游。定时采集默认关闭。

若这份目录对你有用，欢迎 Star 以便之后回来查阅——我们不交换、不购买、不群发 Star。

## 许可

本仓库脚本建议采用 MIT；原创说明的内容许可由维护者确认。第三方项目权利归各自权利人，本仓库不做全文镜像。
