"""把消息交给转发层，并把结果汇总后记进排期层。"""

import anyio

from notify_hub.forwarder import deliver
from notify_hub.store import STATUS_FAILED, STATUS_SENT

# 一个启用中的通道都没有时，消息一条也发不出去，记这个原因。
NO_ENABLED_CHANNEL_ERROR = "没有启用中的通道"


def summarize_deliveries(deliveries):
    """把逐通道结果汇总成消息级的状态、尝试次数与最后错误。

    没有任何通道（例如一个都没启用）时算失败：一条都没发出去，
    不能因为 all([]) 为真就把消息标成“已发”。
    """
    if not deliveries:
        return STATUS_FAILED, 0, NO_ENABLED_CHANNEL_ERROR
    status = STATUS_SENT if all(d.success for d in deliveries) else STATUS_FAILED
    attempts = max(d.attempts for d in deliveries)
    last_error = next((d.error for d in reversed(deliveries) if not d.success), None)
    return status, attempts, last_error


async def send_now(store, forwarder, title, body, *, wait=anyio.sleep):
    """把一条消息发给所有启用中的通道，返回消息编号。"""
    channels = store.list_enabled_channels()
    deliveries = await deliver(forwarder, channels, title, body, wait=wait)
    status, attempts, last_error = summarize_deliveries(deliveries)
    return store.add_message(
        title, body, status, deliveries, attempts=attempts, last_error=last_error
    )
