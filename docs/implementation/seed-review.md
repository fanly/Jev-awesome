# Seed Review（待维护者确认）

生成时间：2026-09-19

所有条目默认为 **proposed**，尚未 curated。reviewer 未填写为 fanly。

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

## 采纳示例

```bash
uv run jev-awesome review show github:1357590729
uv run jev-awesome review approve github:1357590729 --reviewer YOUR_GITHUB_LOGIN --note "source-checked official SDK"
uv run jev-awesome render
```
