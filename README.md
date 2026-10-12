# notify-hub

自建的提醒与通知服务。目标：让 AI 在指定的时间，把一条消息发到我的所有设备。

状态：**方案阶段，还没有代码。** 下一件产出是方案文档（架构、接口、数据表）。

术语见 [GLOSSARY.md](./GLOSSARY.md)。已定的决策见 [docs/adr/](./docs/adr/)。

## 已定

- 只做通知。不做去重、不做静默，这两件事交给监控工具（[ADR 0004](./docs/adr/0004-delivery-only-no-dedup.md)）。
- 通道要能扩展。现在有 Bark 和 ntfy，以后可能加微信。
- iPhone 继续用 Bark。
- 部署在 Windows NAS 上，用 Docker。
- 时间由 AI 换算成绝对时间，再交给服务。
- 排期的跨度要长。
- 入口用远程 MCP（streamable HTTP），不用本地 stdio（[ADR 0003](./docs/adr/0003-schedule-in-remote-service.md)）。
- 转发层用 Apprise，排期层和入口自己写（[ADR 0001](./docs/adr/0001-use-apprise-for-fanout-own-scheduler.md)）。
- 对公网只暴露入口一个地址，并且每次请求都要带令牌（[ADR 0002](./docs/adr/0002-expose-only-the-ingress.md)）。
- 内网穿透用节点小宝。已确认：有 HTTPS，带宽 2 Mbps。

## 未定

- 反向代理现在做，还是只预留路径。
- 投递失败是否重试、重试几次。
- 排期的跨度上限、时区、已发消息的保留条数。

## 参考

- Apprise（转发层，仍在维护）：https://github.com/caronc/apprise
- MIND（已否决的候选，Docker 镜像最后更新 2024-11-23）：https://github.com/Casvt/MIND
- ntfy（通道之一，自带排期能力，但到不了 Bark 和微信）：https://github.com/binwiederhier/ntfy
- pi 支持 stdio 与 streamable HTTP 两种 MCP 传输，不支持旧式 SSE。
- 节点小宝：内网穿透按域名访问，例如 `xxx.iepose.cn`。
