# 排期放在常驻服务里，用远程 MCP 接入

排期必须在我关闭 pi 之后仍然有效。所以排期不能放在 agent 进程里（本地 MCP 或扩展）。服务作为常驻进程跑在 Windows NAS 上，pi 通过 streamable HTTP 连接它。

## Considered Options

- **本地 MCP（stdio）**：pi 启动的子进程。pi 一关，排期就没了。否决。
- **pi 扩展**：同样只在 pi 运行时有效。否决。

## Consequences

- 要处理地址、令牌和 TLS。TLS 由节点小宝的内网穿透提供（已确认有 HTTPS）。
- pi 不支持旧式 SSE，端点必须是 streamable HTTP。
- 服务重启不能丢排期，所以排期要落盘（SQLite）。
