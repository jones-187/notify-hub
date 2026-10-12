"""排期层：到点发送、可注入时钟、重启恢复。

接缝是 Store 与 scheduler 的公开接口；转发层出口、时钟与等待都由测试注入。
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from notify_hub.scheduler import run_loop, tick
from notify_hub.store import STATUS_PENDING, STATUS_SENT, Store

pytestmark = pytest.mark.anyio

TZ = ZoneInfo("Asia/Shanghai")


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


class RecordingStore(Store):
    """记录 cleanup 被调用次数的 Store，用来验证循环会定期触发清理。"""

    def __init__(self, path):
        super().__init__(path)
        self.cleanup_calls = 0

    def cleanup(self, **kwargs):
        self.cleanup_calls += 1
        return super().cleanup(**kwargs)


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


async def test_run_loop_runs_cleanup_at_configured_interval(tmp_path, forwarder, wait):
    store = RecordingStore(tmp_path / "notify.db")
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
        )

    # 每 3 秒清理一次；循环 8 步（时钟推进 8 秒）应触发 2 次
    assert store.cleanup_calls == 2
