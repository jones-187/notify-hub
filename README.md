# notify-hub

自建的提醒与通知服务。目标：让 AI 在指定的时间，把一条消息发到我的所有设备。

状态：**方案阶段，还没有代码。**

术语见 [GLOSSARY.md](./GLOSSARY.md)。

## 已定

- 只做通知。不做去重、不做静默，这两件事交给监控工具。
- 通道要能扩展。现在有 Bark 和 ntfy，以后可能加微信。
- iPhone 继续用 Bark。
- 部署在 Windows NAS 上，用 Docker。
- 时间由 AI 换算成绝对时间，再交给服务。
- 排期的跨度要很长。
- 入口用远程 MCP（streamable HTTP），不用本地 stdio。
- 内网穿透用节点小宝。

## 未定

- 排期层用现成的 MIND，还是自己写一个薄服务。当前倾向：自己写薄的，转发层用 Apprise。
- 反向代理现在做，还是只预留路径。
- 节点小宝免费额度是否提供固定域名与 HTTPS。

## 参考

- Apprise（转发层候选，仍在维护）：https://github.com/caronc/apprise
- MIND（排期层候选，Docker 镜像最后更新 2024-11-23）：https://github.com/Casvt/MIND
- ntfy（通道之一，自带排期能力）：https://github.com/binwiederhier/ntfy
- pi 支持 stdio 与 streamable HTTP 两种 MCP 传输，不支持旧式 SSE。
