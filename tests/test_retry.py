"""投递语义：失败通道重试、成功通道不重发、失败原因入库。

接缝是服务的 HTTP 边界；转发层出口与重试等待都由测试注入。
"""

import pytest

pytestmark = pytest.mark.anyio

AUTH = {"Authorization": "Bearer test-token"}


async def test_failed_channel_is_retried_three_times_with_increasing_waits(
    client, store, forwarder, wait
):
    store.add_channel("fake://broken")
    forwarder.fail_urls = {"fake://broken"}

    resp = await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )

    assert resp.status_code == 200
    # 首发 1 次 + 重试 3 次
    assert forwarder.call_counts() == {"fake://broken": 4}
    # 每次重试前等一次，间隔递增，且测试没有真的等待
    assert len(wait.delays) == 3
    assert wait.delays == sorted(wait.delays)
    assert all(delay > 0 for delay in wait.delays)


async def test_successful_channel_is_never_resent(client, store, forwarder):
    store.add_channel("fake://ok")
    store.add_channel("fake://broken")
    forwarder.fail_urls = {"fake://broken"}

    await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )

    # 成功的通道只被调用一次；只有失败的通道在重试
    assert forwarder.call_counts() == {"fake://ok": 1, "fake://broken": 4}


async def test_transient_failure_recovers_on_retry(client, store, forwarder):
    store.add_channel("fake://flaky")
    forwarder.fail_times = {"fake://flaky": 2}

    resp = await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )

    assert resp.status_code == 200
    stored = store.get_message(resp.json()["id"])
    assert stored.status == "已发"
    assert forwarder.call_counts() == {"fake://flaky": 3}
    assert stored.channel_results == [
        {"channel_id": 1, "success": True, "error": None, "attempts": 3}
    ]


async def test_persistent_failure_records_attempts_and_last_error(
    client, store, forwarder
):
    store.add_channel("fake://broken")
    forwarder.fail_urls = {"fake://broken"}

    resp = await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )

    stored = store.get_message(resp.json()["id"])
    assert stored.status == "失败"
    assert stored.attempts == 4
    assert stored.last_error == "发送失败：fake://broken"
