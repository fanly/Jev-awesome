# Contributing

感谢关注 Jev-awesome。

## 提交资源

请用 Issue 模板提供：

- 原始 URL
- 解决什么问题
- 与 Jev / TypeSafe 的关系与证据
- 已知限制

自动采集只会进入待审队列，**不会**自动成为精选。

## 本地开发

```bash
uv sync --frozen
uv run pytest
uv run ruff check .
uv run jev-awesome validate
```

## 审核

维护者使用 `jev-awesome review approve|reject`。`--reviewer` 仅为审计元数据，不是权限凭据。

## 行为准则

- 不搬运无授权全文
- 不夸大验证等级
- 不把同名无关项目标为 Jev 生态
