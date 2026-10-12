"""排期层：后台循环，到点取出消息并复用转发层送出。"""

import functools

import anyio

from notify_hub.forwarder import deliver
from notify_hub.messaging import summarize_deliveries
from notify_hub.store import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TARGET_BYTES,
    utc_now,
)

# 清理的默认间隔（秒）：后台循环按此时长定期回收数据库空间。
DEFAULT_CLEANUP_INTERVAL = 60.0


async def tick(store, forwarder, *, now=utc_now, wait=anyio.sleep, limit=50):
    """检查一次到期的消息，最多取 limit 条并逐条发送。

    时钟 now 与重试等待 wait 都可注入；发送复用 forwarder.deliver。
    """
    due = store.fetch_due_messages(now(), limit)
    for message in due:
        channels = store.get_channels(message.channels)
        deliveries = await deliver(
            forwarder,
            channels,
            message.title,
            message.body,
            priority=message.priority,
            wait=wait,
        )
        status, attempts, last_error = summarize_deliveries(deliveries)
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
    cleanup_interval=DEFAULT_CLEANUP_INTERVAL,
    max_bytes=DEFAULT_MAX_BYTES,
    target_bytes=DEFAULT_TARGET_BYTES,
):
    """每秒检查一次到期的消息，并按 cleanup_interval 定期清理旧消息。

    启动：在异步上下文里调用本函数；停止：取消该任务。
    清理不是只在启动时跑一次，而是每隔 cleanup_interval 秒跑一次。
    清理里的 VACUUM 会重写整库，放到线程池里执行，不阻塞排期循环和请求处理。
    """
    last_cleanup = now()
    while True:
        await tick(store, forwarder, now=now, wait=wait, limit=limit)
        current = now()
        if (current - last_cleanup).total_seconds() >= cleanup_interval:
            await anyio.to_thread.run_sync(
                functools.partial(
                    store.cleanup, max_bytes=max_bytes, target_bytes=target_bytes
                )
            )
            last_cleanup = current
        await sleep(interval)
