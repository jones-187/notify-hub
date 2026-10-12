"""立刻把一条消息交给转发层，并把结果记进排期层。"""

import anyio

from notify_hub.forwarder import deliver
from notify_hub.store import STATUS_FAILED, STATUS_SENT


async def send_now(store, forwarder, title, body, *, wait=anyio.sleep):
    """把一条消息发给所有启用中的通道，返回消息编号。"""
    channels = store.list_enabled_channels()
    deliveries = await deliver(forwarder, channels, title, body, wait=wait)
    status = STATUS_SENT if all(d.success for d in deliveries) else STATUS_FAILED
    attempts = max((d.attempts for d in deliveries), default=0)
    last_error = next((d.error for d in reversed(deliveries) if not d.success), None)
    return store.add_message(
        title, body, status, deliveries, attempts=attempts, last_error=last_error
    )
