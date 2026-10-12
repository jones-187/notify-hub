# 转发层用 Apprise，排期层自己实现

需要一个能按时间送消息、并能扩展到多个通道的服务。备选是现成的 MIND（自带排期、界面，内部用 Apprise），或自己实现排期与 MCP、把“发给谁”交给 Apprise。

我们决定：转发层用 Apprise，排期层和入口自己实现。理由：MIND 的 Docker 镜像最后更新于 2024-11-23，已接近两年没更新；它的登录页和管理后台要暴露到公网，风险比自己写一个小接口大。Apprise 仍在维护，且已覆盖 Bark、ntfy、企业微信、企业微信机器人、WxPusher、ServerChan 等通道，所以“以后加微信”这一层不需要自己写。自己实现的部分只有：一张存未来消息的表、一个到点检查的循环、几个 MCP 工具。

## Considered Options

- **MIND**：有现成界面与完整 API（`/api/reminders`、`/api/notificationservices` 等，`/api/auth/login` 换 1 小时有效的 API key）。否决原因见上：镜像停更，且必须把网页应用暴露到公网。
- **ntfy 自带的排期**：只能把消息送给 ntfy 客户端，到不了 Bark 和微信系通道。否决。

## Consequences

- 没有现成的管理界面。要手动改某条排期，只能用 MCP 或直接改数据库。
- 以后若想有界面，可以另外跑一个 MIND，只在局域网内访问，不暴露到公网。
