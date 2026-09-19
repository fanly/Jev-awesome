# Security

- 不要在 Issue/PR 中粘贴 API Key 或 token。
- 秘密仅通过环境变量 / Actions Secrets 注入。
- 采集器拒绝 localhost、内网与非允许域名；Authorization 头不跨域转发。
- PR CI 不使用 `pull_request_target` 执行外部代码。
- 发现漏洞请开私密安全公告或私信维护者；本仓库不公布个人邮箱。
