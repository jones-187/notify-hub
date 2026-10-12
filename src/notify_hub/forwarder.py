"""转发层：把一条消息送到多个通道。

真正的发送通过 Apprise 库完成；测试注入假的转发层出口。
"""

from dataclasses import dataclass
from typing import Protocol

import anyio
import apprise


@dataclass(frozen=True)
class DeliveryResult:
    """一个通道一次发送的结果。"""

    success: bool
    error: str | None = None


@dataclass(frozen=True)
class ChannelDelivery:
    """一个通道发送的最终结果，连同通道编号与尝试次数。"""

    channel_id: int
    success: bool
    error: str | None = None
    attempts: int = 1


class Forwarder(Protocol):
    """转发层出口。每个通道每次尝试调用一次。"""

    def send(self, apprise_url: str, title: str, body: str) -> DeliveryResult: ...


class AppriseForwarder:
    """真实的转发层出口：用 Apprise 库发送。

    同步阻塞，由调用方放到线程池里执行。
    """

    def __init__(self, timeout=5):
        self._timeout = timeout

    def send(self, apprise_url, title, body):
        apprise_obj = apprise.Apprise()
        if not apprise_obj.add(apprise_url):
            return DeliveryResult(success=False, error=f"通道地址无效：{apprise_url}")
        with apprise_obj.notify(
            title=title, body=body, timeout=self._timeout
        ) as result:
            if result.status == apprise.AppriseResultStatus.SUCCESS:
                return DeliveryResult(success=True)
            return DeliveryResult(success=False, error=self._failure_text(result))

    @staticmethod
    def _failure_text(result):
        messages = [str(entry.message) for entry in result.logs()]
        return "; ".join(messages) or "发送失败"


# 失败后重试的间隔（秒），逐次递增；共重试 3 次。
DEFAULT_RETRY_DELAYS = (1.0, 2.0, 4.0)


async def deliver(
    forwarder: Forwarder,
    channels,
    title,
    body,
    *,
    retry_delays=DEFAULT_RETRY_DELAYS,
    wait=anyio.sleep,
):
    """逐通道发送一条消息，返回每个通道的最终结果。

    发送放到线程池里执行，不阻塞请求处理。
    只有失败的通道会重试：重试间隔取自 retry_delays（递增），
    成功的通道只发一次，绝不重发。等待函数可注入，测试不真等。
    """
    deliveries = []
    for channel in channels:
        result, attempts = await _deliver_with_retry(
            forwarder, channel, title, body, retry_delays, wait
        )
        deliveries.append(
            ChannelDelivery(
                channel_id=channel.id,
                success=result.success,
                error=result.error,
                attempts=attempts,
            )
        )
    return deliveries


async def _deliver_with_retry(
    forwarder: Forwarder, channel, title, body, retry_delays, wait
):
    attempt = 0
    while True:
        result = await anyio.to_thread.run_sync(
            forwarder.send, channel.apprise_url, title, body
        )
        attempt += 1
        if result.success or attempt > len(retry_delays):
            return result, attempt
        await wait(retry_delays[attempt - 1])
