# 09: 优先级

**What to build:** 每条消息可以带一个优先级，服务把它带到底层通道上。内网 `POST /notify` 增加可选字段 `priority`。

**Blocked by:** 08

**Status:** done（2026-10-13，本地全绿）

设计见 [ADR 0005](../../../docs/adr/0005-carry-priority-in-channel-address.md)。

- [x] 四档 `low` / `normal` / `high` / `urgent`，默认 `normal`，也接受数字 1-5。
- [x] 不认识的档位返回 400，不静默猜一个。
- [x] 内网 `POST /notify` 接受可选 `priority`。
- [x] 存进库（`messages` 新增列 `priority`），**旧的库自动补列**，老消息读出来算普通档。
- [x] 排期的消息到点发送时带自己的档位。
- [x] 用**真实 Apprise** 断言档位确实被解析出来（`NotifyNtfy.priority` / `NotifyBark.level`）。
- [ ] 在 NAS 上部署后，真机验证一次：发一条 `urgent`，在 ntfy 的消息缓存里看到 priority 5。

## 暂不做

- MCP 的 `send_message` / `schedule_message` **暂不开放** `priority` 参数：AI 目前不需要按优先级区分。
  要开的时候是纯增量的（存储层和转发层已经通了，入口加一个可选参数即可）。
