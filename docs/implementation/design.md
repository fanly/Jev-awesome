# 设计说明（实际采用）

## 数据流

```text
sources.yaml 配置
    ↓
adapters（GitHub / RSS / 官方监测 / Issue 导入）
    ↓
observations/（机器事实快照，可覆盖更新）
    ↓
normalize + dedupe（稳定实体 ID）
    ↓
classification（rules 默认；可选 typesafe-sdk）
    ↓
inbox/ pending 候选（建议字段，不改人工结论）
    ↓
review CLI（approve / reject / merge / archive）
    ↓
resources/ 权威条目 + decisions/ + events/
    ↓
render（README / 分类页 / 周报）+ site build
    ↓
automation（dry-run / write-local / 可选远端 PR）
```

## 权责边界

| 角色 | 可写 | 不可写 |
|---|---|---|
| 采集器 | observations、inbox 建议、run report | editorial_status、人工摘要、验证等级、精选输出 |
| 规则/模型分类 | suggestion_* 字段、原因码 | curated、reproduced、license 结论 |
| 审核 CLI | 状态迁移、人工字段、事件 | 工作流、依赖、权限配置 |
| 渲染器 | 受控生成区 / 生成文件 | 人工介绍段落（若分隔） |
| 机器人 PR | 允许数据路径与生成文件 | 源码、workflows、LICENSE、人工决策 |

## 稳定身份

- GitHub：`github:{repository_id}`，full_name/URL 可变。
- 非 GitHub：首次分配 `res:{uuid4}` 或 `web:{sha256(canonical_url)[:16]}`，URL 变更走 aliases。
- 去重：规范化 URL（去跟踪参数）+ repo id；模糊标题只建议不合并。

## 人工字段保护

资源文件拆分逻辑字段组：

- `machine` / observations：可被采集更新
- `editorial`：summary、jev_role、limitations、verification、review_record —— 采集只写 suggestions，合并时永不覆盖非空 editorial

## 分类器模式

- `rules`（默认）：确定性关键词/域名/topic 规则，零模型调用
- `auto`：显式选择且 Key 存在才调用 TypeSafe，否则回退 rules 并记录
- `typesafe`：强制真实 SDK；缺 Key 失败

问题设计（同一次 system_one，互不依赖）：

1. Noul：是否与 TypeSafe/Jev System One 主题相关
2. Choice：resource_kind（含 `unrelated` / `insufficient_evidence`）
3. Choice：jev_relationship（含 `unclear`）
4. Score：审查优先级（低/中/高）

## 自动化简化取舍

- 三个 workflow：`ci.yml` / `collect.yml` / `pages.yml`
- 机器人分支：`automation/catalog-update`；最多一个开放汇总 PR
- 下一轮采集：读取未合并机器人分支允许数据文件并合并，避免从 main 重建丢候选
- 人工修改机器人分支：暂停自动覆盖
- 默认 `COLLECTOR_ENABLED=false`、`AUTO_PR_ENABLED=false`、`PAGES_ENABLED=false`
- 首版静态站：Jinja2 + 少量 JS；子路径 `/Jev-awesome/`

## 不做

登录、支付、CMS、向量库、MCP、需登录抓取、自动执行第三方代码、自动合并精选、自由文本摘要 LLM。
