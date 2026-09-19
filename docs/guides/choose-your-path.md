# 官方 API、社区 SDK、LocalJev、kev：应该从哪里开始？

目标不是「收集最多仓库」，而是**按你现在的约束选一条最小路径**。

## 决策树（从你自己的约束出发）

1. **你要接生产、且有 TypeSafe 账号与预算？**  
   → 官方 **Python / JS SDK** + [docs llms.txt](https://docs.typesafe.ai/llms.txt) + [Primitives](https://docs.typesafe.ai/primitives) / [Confidence](https://docs.typesafe.ai/confidence)。  
   先跑通一次 `system_one`，再嵌进业务。

2. **你要先学问题设计，还不想绑死语言？**  
   → 读官方 **skills**（`typesafe-ai/skills`）里的 `SKILL.md`，用代理帮你起草 Choice/Noul；真正调用仍走官方 SDK。

3. **没有官方 Key，只想联调客户端形状？**  
   → 官方 **system-one-adapter-python**（LLM 替身）或社区 **LocalJev**（本地兼容 `/v1/systemone`）。  
   明确写在代码注释里：这是替身/兼容实现，**不是**官方 Jev 质量承诺。

4. **你在研究「如何训练/读出概率决策头」？**  
   → **kev**（独立权重 + 冻结评测叙述）。可把官方 SDK 的 `base_url` 指到本地服务做形状兼容实验。  
   不要把 kev 榜上的数字直接写成「官方 Jev 成绩」。

5. **你要对照延迟/成本/判断形态？**  
   → 读 **typesafe-ai-benchmark** 的方法与原始导出；把它当作者实验记录。  
   本目录**没有**重跑该基准，因此不会把它标成 `benchmarked`。

6. **你要看垂直场景怎么接？**  
   → 浏览器：**jev-ultrafast**；Android：**mobile-jev**；Postgres：**pg-jev**；Neo4j：**neo4jev**。  
   各自依赖设备、数据库或第二把文本模型 Key——先读该条目的「限制」。

## 名称易混，请钉死身份

| 名字 | 身份（本目录口径） |
|---|---|
| TypeSafe / Jev / System One | 官方托管判断 API |
| typesafe-sdk / typesafe-sdk-js | 官方客户端 |
| system-one-adapter-python | 官方提供的**替身**适配器 |
| LocalJev | 社区/研究向**兼容实现** |
| kev | **独立**训练的决策模型族，API 形状对齐 |
| 各种 awesome-jev | 导航目录，不是实现证据 |

## 建议的第一周顺序

1. 读 [start-here](start-here.md) 把步骤拆开  
2. 读 primitives + confidence  
3. 按官方 [typesafe-sdk-python](https://github.com/typesafe-ai/typesafe-sdk-python) Quickstart 打通一次真实 `system_one`（需 Key）  
4. 再选一个垂直仓库读「先读 / 依赖」字段里的文件

其他 Awesome 列表只放在 README 底部作生态导航，**不计入**本目录首批精选核心。
