"""排期层：到点发送、可注入时钟、重启恢复。

接缝是 Store 与 scheduler 的公开接口；转发层出口、时钟与等待都由测试注入。
"""

import os
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from zoneinfo import ZoneInfo

import anyio
import pytest

from notify_hub.forwarder import ChannelDelivery
from notify_hub.scheduler import run_loop, tick
from notify_hub.store import STATUS_FAILED, STATUS_PENDING, STATUS_SENT, Store

pytestmark = pytest.mark.anyio

TZ = ZoneInfo("Asia/Shanghai")

# 很小的阈值：SQLite 空库约 16 KB，所以上限设在几十 KB，测试数据也就几十 KB。
MAX_BYTES = 24 * 1024
TARGET_BYTES = 20 * 1024


class FakeClock:
    """可手动推进的时钟：测试把“现在”设到某一刻再前进几秒，绝不真等。"""

    def __init__(self, now):
        self._now = now

    def now(self):
        return self._now

    def advance(self, seconds):
        self._now += timedelta(seconds=seconds)


class StopLoop(Exception):
    pass


class FakeSleep:
    """假的循环等待：记录等待时长，到次数后抛异常停止循环。"""

    def __init__(self, stop_after):
        self.delays = []
        self.stop_after = stop_after

    async def __call__(self, delay):
        self.delays.append(delay)
        if len(self.delays) >= self.stop_after:
            raise StopLoop()


class AdvancingSleep:
    """假的循环等待：每次把时钟推进一步，到次数后停止循环。"""

    def __init__(self, clock, stop_after):
        self.clock = clock
        self.stop_after = stop_after
        self.calls = 0

    async def __call__(self, delay):
        self.clock.advance(delay)
        self.calls += 1
        if self.calls >= self.stop_after:
            raise StopLoop()


class SlowCleanupStore(Store):
    """清理时在后台线程里真停一下，用来证明事件循环没被挡住。"""

    def __init__(self, path, hold_seconds):
        super().__init__(path)
        self._hold_seconds = hold_seconds
        self.started_at = None
        self.finished_at = None

    def cleanup(self, **kwargs):
        self.started_at = time.monotonic()
        time.sleep(self._hold_seconds)
        self.finished_at = time.monotonic()
        return 0


def test_schedule_message_stores_pending_message_with_all_columns(store):
    store.add_channel("fake://one")
    scheduled = datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ)
    now = datetime(2026, 10, 13, 7, 0, 0, tzinfo=timezone.utc)

    message_id = store.schedule_message(
        "标题", "正文", [1], scheduled, now=now
    )

    stored = store.get_message(message_id)
    assert stored.id == message_id
    assert stored.title == "标题"
    assert stored.body == "正文"
    assert stored.channels == [1]
    # 库里存 UTC，对外是带时区的 RFC3339 字符串
    assert stored.scheduled_at == "2026-10-13T00:00:00+00:00"
    assert stored.created_at == "2026-10-13T07:00:00+00:00"
    assert stored.status == STATUS_PENDING
    assert stored.attempts == 0
    assert stored.last_error is None
    assert stored.channel_results == []


async def test_tick_sends_due_message_and_marks_sent(store, forwarder, wait):
    store.add_channel("fake://one")
    scheduled = datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ)
    message_id = store.schedule_message("标题", "正文", [1], scheduled)
    clock = FakeClock(scheduled)

    sent = await tick(store, forwarder, now=clock.now, wait=wait)

    assert [m.id for m in sent] == [message_id]
    assert forwarder.calls == [
        {"apprise_url": "fake://one", "title": "标题", "body": "正文"}
    ]
    stored = store.get_message(message_id)
    assert stored.status == STATUS_SENT
    assert stored.channel_results == [
        {"channel_id": 1, "success": True, "error": None, "attempts": 1}
    ]


async def test_tick_does_not_send_future_message_until_clock_advances(
    store, forwarder, wait
):
    store.add_channel("fake://one")
    scheduled = datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ)
    message_id = store.schedule_message("标题", "正文", [1], scheduled)
    clock = FakeClock(datetime(2026, 10, 13, 7, 59, 59, tzinfo=TZ))

    sent = await tick(store, forwarder, now=clock.now, wait=wait)

    assert sent == []
    assert forwarder.calls == []

    clock.advance(2)
    sent = await tick(store, forwarder, now=clock.now, wait=wait)

    assert [m.id for m in sent] == [message_id]
    assert forwarder.calls == [
        {"apprise_url": "fake://one", "title": "标题", "body": "正文"}
    ]


async def test_tick_fails_due_message_when_no_enabled_channel(store, forwarder, wait):
    # 通道被停用后，到点的消息一条也发不出去，要标成失败并写清原因。
    store.add_channel("fake://disabled", enabled=False)
    scheduled = datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ)
    message_id = store.schedule_message("标题", "正文", [1], scheduled)
    clock = FakeClock(scheduled + timedelta(seconds=1))

    sent = await tick(store, forwarder, now=clock.now, wait=wait)

    assert [m.id for m in sent] == [message_id]
    assert forwarder.calls == []
    stored = store.get_message(message_id)
    assert stored.status == STATUS_FAILED
    assert stored.attempts == 0
    assert stored.last_error == "没有启用中的通道"


async def test_restart_recovery_sends_pending_message_from_same_db_file(
    tmp_path, forwarder, wait
):
    db_path = tmp_path / "notify.db"
    scheduled = datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ)

    first = Store(db_path)
    first.add_channel("fake://one")
    message_id = first.schedule_message("标题", "正文", [1], scheduled)

    # 用同一个数据库文件新建一个 Store 实例，模拟服务重启
    restarted = Store(db_path)
    clock = FakeClock(scheduled + timedelta(seconds=1))

    sent = await tick(restarted, forwarder, now=clock.now, wait=wait)

    assert [m.id for m in sent] == [message_id]
    assert restarted.get_message(message_id).status == STATUS_SENT


async def test_tick_sends_at_most_50_messages_per_pass(store, forwarder, wait):
    store.add_channel("fake://one")
    scheduled = datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ)
    for _ in range(60):
        store.schedule_message("标题", "正文", [1], scheduled)
    clock = FakeClock(scheduled + timedelta(seconds=1))

    first_pass = await tick(store, forwarder, now=clock.now, wait=wait)

    assert len(first_pass) == 50
    assert len(forwarder.calls) == 50

    second_pass = await tick(store, forwarder, now=clock.now, wait=wait)

    assert len(second_pass) == 10
    assert len(forwarder.calls) == 60


async def test_run_loop_checks_due_messages_every_second(store, forwarder, wait):
    # 循环的节拍（每隔多久检查一次）只有注入的 sleep 能看到；发一条请求看不到
    # “两次检查之间隔了多久”，所以这里保留对等待时长的断言，作为唯一能证明
    # “按 interval 检查”的证据。
    sleep = FakeSleep(stop_after=2)
    clock = FakeClock(datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ))

    with pytest.raises(StopLoop):
        await run_loop(
            store,
            forwarder,
            interval=1.0,
            now=clock.now,
            sleep=sleep,
            wait=wait,
        )

    assert sleep.delays == [1.0, 1.0]


async def test_run_loop_keeps_event_loop_free_while_cleanup_runs(
    tmp_path, forwarder, wait
):
    # 清理里的 VACUUM 会重写整库。清理必须放到线程池里跑，否则会挡住事件循环
    # （既挡排期循环也挡请求处理）。用一个会真的阻塞一小会儿的清理，加一个
    # 并发的“心跳”，看心跳能不能落在清理进行中。
    store = SlowCleanupStore(tmp_path / "notify.db", hold_seconds=0.3)
    clock = FakeClock(datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ))
    heartbeats = []

    async def heartbeat():
        while True:
            heartbeats.append(time.monotonic())
            await anyio.sleep(0.01)

    async def sleep_forever(_delay):
        await anyio.sleep_forever()

    loop = partial(
        run_loop,
        store,
        forwarder,
        interval=1.0,
        now=clock.now,
        sleep=sleep_forever,
        wait=wait,
        cleanup_interval=0.0,
    )

    with anyio.move_on_after(2.0):
        async with anyio.create_task_group() as tg:
            tg.start_soon(heartbeat)
            tg.start_soon(loop)
            while store.finished_at is None:
                await anyio.sleep(0.005)
            tg.cancel_scope.cancel()

    inside = [t for t in heartbeats if store.started_at < t < store.finished_at]
    assert inside, "cleanup 同步执行，事件循环在清理期间被挡住了"


def fill_sent(store, count):
    """造 count 条已发消息，用来把库催到超过保留上限。"""
    ids = []
    for i in range(count):
        ids.append(
            store.add_message(
                f"标题{i}",
                "正文",
                STATUS_SENT,
                [ChannelDelivery(channel_id=1, success=True)],
            )
        )
    return ids


async def test_run_loop_runs_cleanup_at_configured_interval(tmp_path, forwarder, wait):
    db_path = tmp_path / "notify.db"
    store = Store(db_path)
    store.add_channel("fake://one")
    sent_ids = fill_sent(store, 200)
    size_before = os.path.getsize(db_path)
    assert size_before > MAX_BYTES
    clock = FakeClock(datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ))
    sleep = AdvancingSleep(clock, stop_after=8)

    with pytest.raises(StopLoop):
        await run_loop(
            store,
            forwarder,
            interval=1.0,
            now=clock.now,
            sleep=sleep,
            wait=wait,
            cleanup_interval=3.0,
            max_bytes=MAX_BYTES,
            target_bytes=TARGET_BYTES,
        )

    # 不看 cleanup 被调了几次，只看外部状态：旧的已发消息真的被删了、库文件真的变小了。
    # 循环跑 8 步、每 3 秒清理一次，所以确实在循环里跑到过清理。
    assert os.path.getsize(db_path) < size_before
    assert any(store.get_message(mid) is None for mid in sent_ids)
