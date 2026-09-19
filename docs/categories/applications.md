# 应用与工具 / Applications & Tools

<!-- JEV-AWESOME:GENERATED-START -->
本页由权威数据生成。仅包含 **curated** 精选。


## browser-use/jev-ultrafast

- 链接：[https://github.com/browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast)
- 解决什么问题：学习「决策与文本生成解耦」的可运行浏览器 Agent；先读 agent 循环比抄提示词更有用。
- Jev 角色：一次请求内选出 CLICK/TYPE_TEXT/… 与目标元素索引；不生成页面文案。
- 先读 / 依赖：依赖：uv、Chrome + Browser Harness、TYPESAFE_API_KEY、TEXT_MODEL_API_KEY（示例为 OpenRouter）。先读：`jev_ultrafast/agent.py` 与 README「The action space」。
- 验证：`code_located`
- 限制：演示延迟/路径依赖真实页面与 Key；本目录未复现其 7.1s 声明。云端 waitlist 与本地 demo 是不同产品面。
- 摘要：Browser Use × TypeSafe：动态编号动作空间；Jev 选 operation/target，仅 TYPE_TEXT 时才让小 LLM 写字。

## droidrun/mobile-jev

- 链接：[https://github.com/droidrun/mobile-jev](https://github.com/droidrun/mobile-jev)
- 解决什么问题：看清手机侧「观察→Jev 决策→执行」链路与本地 studio，而不是又一个聊天 demo。
- Jev 角色：根据屏幕观察在动作候选中做结构化选择；不直接驱动触摸硬件。
- 先读 / 依赖：Node 22+/24、pnpm、MOBILERUN_API_KEY、TYPESAFE_API_KEY、可用 Android 设备（经 Mobilerun）。先读：README「Run it」与 `docs/DEMO.md`；暗色主题 demo 可离线理解流程。
- 验证：`source_checked`
- 限制：设备/云服务单独计费；完整订票类 demo 未演示成交。本目录未接真机复现。
- 摘要：Android 真机 Agent：Mobilerun 观察/执行，Jev 做决策；含 React studio、CLI 与痕迹。

## realZachi/pg-jev

- 链接：[https://github.com/realZachi/pg-jev](https://github.com/realZachi/pg-jev)
- 解决什么问题：把「语义过滤」放进 SQL，而不是在应用层把整表塞进聊天模型。
- Jev 角色：对行级条件返回概率（jev / jev_prob）；不负责生成 SQL 或嵌入。
- 先读 / 依赖：PostgreSQL + 扩展安装（PGXN/构建）；TYPESAFE_API_KEY；网络可达 TypeSafe。先读：上游 README 的 SQL 示例与扩展安装说明。
- 验证：`source_checked`
- 限制：每行/批调用有成本与延迟；许可为 PostgreSQL 类（NOASSERTION 元数据）。本目录未装扩展复现。
- 摘要：PostgreSQL 扩展：用自然语言条件过滤/排序/分类行；每行由 Jev 判概率，无向量列。

## jexp/neo4jev

- 链接：[https://github.com/jexp/neo4jev](https://github.com/jexp/neo4jev)
- 解决什么问题：学习如何用概率路径/beam search 做图遍历，而不是让 LLM 编造下一跳。
- Jev 角色：单跳 Choice（跟哪条边）+ Noul（是否到达）；应用层做 beam 与可视化。
- 先读 / 依赖：Neo4j（默认可指公共 companies2 demo）、TYPESAFE_API_KEY、Python 环境。先读：`src/neo4jev/navigator.py` 与 README Architecture。无 Key 时上游会显式用占位答案，不伪装成 TypeSafe 输出。
- 验证：`code_located`
- 限制：演示图与自建图 schema 不同；本目录未连接 Neo4j/live Jev。
- 摘要：Neo4j 图导航演示：每跳把出边做成 Choice，并同请求问 Noul「是否到达目标」。



<!-- JEV-AWESOME:GENERATED-END -->
