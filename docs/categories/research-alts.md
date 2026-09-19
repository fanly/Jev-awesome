# 研究与替代实现 / Research & Alternatives

<!-- JEV-AWESOME:GENERATED-START -->
本页由权威数据生成。仅包含 **curated** 精选。


## githubnext/localjev

- 链接：[https://github.com/githubnext/localjev](https://github.com/githubnext/localjev)
- 解决什么问题：在无官方 Key 或要本地试验时，对齐 System One 契约做客户端联调。
- Jev 角色：本地兼容端点；不是官方托管 Jev，质量与校准不可直接等同。
- 先读 / 依赖：按上游 README 安装运行时与模型依赖。先读仓库说明与 `/v1/systemone` 兼容说明。
- 验证：`source_checked`
- 限制：名称易与官方混淆；输出≠官方 Jev。本目录未本地启动服务。
- 摘要：GitHub Next：本地兼容 `POST /v1/systemone` 的实现（Bun + Diffusion），用于研究/桥接。

## jaredpalmer/kev

- 链接：[https://github.com/jaredpalmer/kev](https://github.com/jaredpalmer/kev)
- 解决什么问题：研究「概率读出 vs 解码文本」、本地训练与冻结评测套件；可换 base_url 试官方 SDK。
- Jev 角色：独立模型族；API 形状对齐 System One，但权重与校准是作者自己的。
- 先读 / 依赖：Python 3.12+、uv、权重（Hugging Face）、Apple Silicon/CUDA 视规模而定。先读：README Highlights 与 PLAN.md；评测口径见 frozen suites 说明。
- 验证：`source_checked`
- 限制：作者自述部分 checkpoint 未过其发布门槛；数字不可当官方 Jev 成绩。本目录未训练/未服务。
- 摘要：受 Jev 启发的可训练小型决策模型（Qwen + LoRA/读出头）；提供兼容 System One 的服务端。



<!-- JEV-AWESOME:GENERATED-END -->
