# notify-hub

自建的提醒与通知服务。目标：让 AI 在指定的时间，把一条消息发到我的所有设备。

状态：**代码已写完，本地测试 60 个全绿（2026-10-12）。还没部署到 NAS。**

规格见 [.scratch/notify-hub/spec.md](./.scratch/notify-hub/spec.md)，工单见 [.scratch/notify-hub/issues/](./.scratch/notify-hub/issues/)，部署步骤见 [docs/deploy.md](./docs/deploy.md)。

分支：`feat/notify-hub`。

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
- 入口给 AI 4 个工具：`send_message`、`schedule_message`、`list_messages`、`cancel_message`。不做“修改”，改一条等于取消旧的加新建一条。
- 内网端口另开一个普通 HTTP 接口（`POST /notify`），给监控工具和脚本用。
- 投递失败重试 3 次，仍然失败就记一条日志，不改走别的通道。
- 时区固定 `Asia/Shanghai`。时间落在过去就直接报错，不静默改成“现在发”。
- 排期跨度不设上限。
- 反向代理不做，只预留路径。
- 转发层用 Apprise 库（在自己进程里 import），不用 Apprise API 容器。一个容器。
- 已发消息的保留：数据库文件超过 10 MB 时，删最旧的已发消息，降到 8 MB 以下。未发消息永不删。
- 没有启用中的通道时，消息算“失败”，不算“已发”（失败原因写进记录）。
- 公网端口上不提供 OAuth 发现端点，只支持静态 bearer 令牌。

## 还没定

- 清理的删除候选要不要包含“失败”的消息。不包含的话，某条通道一直坏时数据库降不到 8 MB 以下。
- 工单 08（穿透接入与端到端验证）要在 NAS 上做，还没做。

## 参考

- Apprise（转发层，仍在维护）：https://github.com/caronc/apprise
- MIND（已否决的候选，Docker 镜像最后更新 2024-11-23）：https://github.com/Casvt/MIND
- ntfy（通道之一，自带排期能力，但到不了 Bark 和微信）：https://github.com/binwiederhier/ntfy
- pi 支持 stdio 与 streamable HTTP 两种 MCP 传输，不支持旧式 SSE。
- 节点小宝：内网穿透按域名访问，例如 `xxx.iepose.cn`。
