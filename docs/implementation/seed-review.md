# Seed Review（R1 抽查更新）

更新：2026-09-19（R1）  
正式审核状态**未改**：全部仍为 proposed / pending；curated=0。  
`reviewer` 未填写为 fanly；下列「建议」≠采纳。

## 全量 Seed 表（31+；inbox proposed≈34）

| ID | 标题 | 类别 | 验证 | 中文摘要 |
|---|---|---|---|---|
| `web:1ee3f04b85cf2674` | TypeSafe documentation index (llms.txt) | official | source_checked | 有 |
| `web:e8d1402271d73689` | TypeSafe Python SDK docs | sdk_integrations | source_checked | 有 |
| `web:6b79f05c84473e46` | TypeSafe Primitives | getting_started | source_checked | 有 |
| `web:64154f4aee021df4` | TypeSafe Confidence | getting_started | source_checked | 有 |
| `web:d12734b4fa0f4647` | TypeSafe homepage | official | source_checked | 有 |
| `github:1357590729` | typesafe-ai/typesafe-sdk-python | sdk_integrations | source_checked | 有 |
| `github:1357635350` | typesafe-ai/typesafe-sdk-js | sdk_integrations | source_checked | 有 |
| `github:1345508845` | typesafe-ai/skills | official | source_checked | 有 |
| `github:1328238153` | typesafe-ai/system-one-adapter-python | sdk_integrations | source_checked | 有 |
| `github:642065600` | Anil-matcha/awesome-jev-by-typesafe | applications | discovered | 有 |
| `github:1375286981` | fatwang2/awesome-jev | applications | discovered | 有 |
| `github:1374652607` | hellogumbo/awesome-jev | applications | discovered | 有 |
| `github:1375473949` | yzfly/awesome-jev-zh | applications | discovered | 有 |
| `github:1374058281` | AbdelStark/awesome-typesafe | applications | discovered | 有 |
| `github:1375694187` | cobanov/awesome-jev | applications | discovered | 有 |
| `github:1374404623` | AnotiaWang/awesome-jev | applications | discovered | 有 |
| `github:1375482713` | logicrw/awesome-jev-projects | applications | discovered | 有 |
| `github:1374349137` | thruwire/foreman | applications | discovered | 有 |
| `github:1376174149` | githubnext/localjev | research_alts | source_checked | 有 |
| `github:1375069862` | jaredpalmer/kev | research_alts | source_checked | 有 |
| `github:1375639479` | razorback16/openjev | research_alts | source_checked | 有 |
| `github:1376820799` | fritzprix/systemone-lite | research_alts | source_checked | 有 |
| `github:1377163963` | frodi-karlsson/jev-client | sdk_integrations | discovered | 有 |
| `github:1213316537` | typesafe-ai/daggerverse | applications | discovered | 有 |
| `github:1376531520` | Rassl/usejev | applications | discovered | 无 |
| `github:1376573799` | toganio/jev-word-lab | applications | discovered | 无 |
| `github:1376668745` | MoRohn/meridian-copilot | applications | discovered | 无 |
| `github:1376882316` | spprashaant/jevtryout | applications | discovered | 无 |
| `github:1376897483` | umgbhalla/jevx | applications | discovered | 无 |
| `github:1376888319` | nikolas-j/jev-voice-browser | applications | discovered | 无 |
| `github:1376893058` | TheEleventhAvatar/triage-bot | applications | discovered | 无 |

## 代表条目抽查（≥10）

| ID | 区分 | 证据/限制 | 建议纳入？ |
|---|---|---|---|
| `web:d12734b4fa0f4647` | 官方入口 | 官网；非实现 | 是（官方导航） |
| `web:1ee3f04b85cf2674` | 官方资料 | llms.txt 索引 | 是 |
| `github:1357590729` | 官方 SDK | typesafe-ai org；源码可读≠已跑通 | 是（优先） |
| `github:1357635350` | 官方 SDK | JS SDK；同上 | 是 |
| `github:1345508845` | 官方/技能包 | org 仓库；用途需人工读 README | 是（标注技能包） |
| `github:1328238153` | 官方适配器 | System One adapter | 是 |
| `github:1376174149` | 研究/替代 | githubnext/localjev；独立实现 | 是（research） |
| `github:1375069862` | 研究/替代 | kev；名称相近需防混淆 | 条件纳入并写清差异 |
| `github:642065600` | 社区列表 | awesome 聚合；二次来源 | 可作导航，不作唯一证据 |
| `github:1375473949` | 社区列表 | 中文 awesome | 同上 |
| `github:1374349137` | 社区应用 | foreman；需核许可与 Jev 相关度 | 暂缓至读许可 |
| `github:1376531520` | 仅提及/弱证据 | 无中文摘要；discovered | 暂缓 |

许可：未知不填 MIT。README 阅读 ≠ 源码定位 ≠ 运行复现。

## 建议首批采纳（命令未执行）

维护者自行确认后：

```bash
uv run jev-awesome review show github:1357590729
uv run jev-awesome review approve github:1357590729 --reviewer YOUR_GITHUB_LOGIN --note "official Python SDK; source-checked"
uv run jev-awesome review show github:1357635350
uv run jev-awesome review approve github:1357635350 --reviewer YOUR_GITHUB_LOGIN --note "official JS SDK"
uv run jev-awesome render
```
