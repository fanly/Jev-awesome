# SDK 与集成 / SDKs & Integrations

<!-- JEV-AWESOME:GENERATED-START -->
本页由权威数据生成。仅包含 **curated** 精选。


## typesafe-ai/typesafe-sdk-python

- 链接：[https://github.com/typesafe-ai/typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python)
- 解决什么问题：把「在候选中做校准判断」接到任意 Python 服务；是接入官方 Jev 的默认客户端。
- Jev 角色：对 state 上的 typed questions 返回 choice/noul/score 与概率；不负责写散文。
- 先读 / 依赖：依赖：`typesafe-sdk`（或本仓库已声明版本）。需要 `TYPESAFE_API_KEY`。先读：上游 README Quickstart 与 docs.typesafe.ai/sdk/python/。
- 验证：`source_checked`
- 限制：无 Key 无法调真实 Jev；Mock/Adapter 结果≠官方模型。本目录未做 live 复现。
- 摘要：官方 Python SDK（PyPI: typesafe-sdk）。用 `TypeSafeClient.system_one` 提交 Choice / Noul / Score，拿到概率化结构化判断，而不是自由生成文本。

## typesafe-ai/typesafe-sdk-js

- 链接：[https://github.com/typesafe-ai/typesafe-sdk-js](https://github.com/typesafe-ai/typesafe-sdk-js)
- 解决什么问题：在 Node / 浏览器后端侧接入同一套 typed questions，与 Python 团队对齐契约。
- Jev 角色：官方客户端：system_one + Choice/Noul/Score；不替代业务编排。
- 先读 / 依赖：依赖官方 JS SDK 包；需要 TYPESAFE_API_KEY。先读仓库 README 与官方 SDK 文档。
- 验证：`source_checked`
- 限制：需有效 Key；本目录仅 source_checked，未跑通线上调用。
- 摘要：官方 TypeScript/JavaScript SDK，与 Python 客户端同属 System One 调用面。

## typesafe-ai/system-one-adapter-python

- 链接：[https://github.com/typesafe-ai/system-one-adapter-python](https://github.com/typesafe-ai/system-one-adapter-python)
- 解决什么问题：无官方 Key 时仍能联调客户端形状；明确区分「替身」与「真 Jev」。
- Jev 角色：开发/测试替身；结果不等同于 System One / Jev。
- 先读 / 依赖：Python + 上游依赖 + 你自己的 LLM API Key。先读仓库 README。
- 验证：`source_checked`
- 限制：勿当生产替代；概率/校准语义可能完全不同。
- 摘要：官方适配器：用通用 LLM API 充当 TypeSafeClient 替身，便于本地实验。



<!-- JEV-AWESOME:GENERATED-END -->
