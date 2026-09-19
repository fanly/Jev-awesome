# 入门与模式 / Getting Started & Patterns

<!-- JEV-AWESOME:GENERATED-START -->
本页由权威数据生成。仅包含 **curated** 精选。


## TypeSafe Confidence

- 链接：[https://docs.typesafe.ai/confidence.md](https://docs.typesafe.ai/confidence.md)
- 解决什么问题：避免在 Noul 上读不存在的字段，或把 confidence 误当成万能阈值。
- Jev 角色：解释如何解读返回分布上的置信信息。
- 先读 / 依赖：先读 primitives，再读本页。无需 Key。
- 验证：`source_checked`
- 限制：置信度≠业务正确性保证。
- 摘要：官方置信度说明：confidence 仅适用于 Choice/Score；Noul 无 confidence。

## TypeSafe Primitives

- 链接：[https://docs.typesafe.ai/primitives.md](https://docs.typesafe.ai/primitives.md)
- 解决什么问题：设计问题时必读：弄清「选项」「有序档」「是否」三种问题类型。
- Jev 角色：定义你能向 Jev 问什么；本身不是运行时。
- 先读 / 依赖：无 Key。先读本页，再写 SDK 调用。
- 验证：`source_checked`
- 限制：文档会迭代；以线上 docs.typesafe.ai 为准。
- 摘要：官方原语说明：Choice / Score / Noul 的字段语义与同请求隔离。



<!-- JEV-AWESOME:GENERATED-END -->
