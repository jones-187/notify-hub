"""排期层：后台循环，到点取出消息并复用转发层送出。"""

import anyio

from notify_hub.forwarder import deliver
from notify_hub.store import STATUS_FAILED, STATUS_SENT, utc_now


async def tick(store, forwarder, *, now=utc_now, wait=anyio.sleep, limit=50):
    """检查一次到期的消息，最多取 limit 条并逐条发送。

    时钟 now 与重试等待 wait 都可注入；发送复用 forwarder.deliver。
    """
    due = store.fetch_due_messages(now(), limit)
    for message in due:
        channels = store.get_channels(message.channels)
        deliveries = await deliver(
            forwarder, channels, message.title, message.body, wait=wait
        )
        status = STATUS_SENT if all(d.success for d in deliveries) else STATUS_FAILED
        attempts = max((d.attempts for d in deliveries), default=0)
        last_error = next(
            (d.error for d in reversed(deliveries) if not d.success), None
        )
        store.update_message_status(
            message.id, status, deliveries, attempts=attempts, last_error=last_error
        )
    return due


async def run_loop(
    store,
    forwarder,
    *,
    interval=1.0,
    now=utc_now,
    sleep=anyio.sleep,
    wait=anyio.sleep,
    limit=50,
):
    """每秒检查一次到期的消息，直到被取消。

    启动：在异步上下文里调用本函数；停止：取消该任务。
    """
    while True:
        await tick(store, forwarder, now=now, wait=wait, limit=limit)
        await sleep(interval)
