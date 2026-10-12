"""内网端口的只读接口 GET /messages。

接缝是内网端口的 HTTP 边界；数据库与转发层出口都由测试注入。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.anyio

AUTH = {"Authorization": "Bearer test-token"}
TZ = ZoneInfo("Asia/Shanghai")


async def test_messages_without_token_returns_401(client):
    response = await client.get("/messages")

    assert response.status_code == 401


async def test_messages_is_read_only(client):
    response = await client.post("/messages", headers=AUTH, json={})

    assert response.status_code == 405


async def test_messages_lists_pending_first_then_recently_sent(client, store):
    store.add_channel("fake://one")
    pending_id = store.schedule_message(
        "稍后", "正文", [1], datetime(2026, 10, 13, 9, 0, tzinfo=TZ)
    )
    sent = await client.post(
        "/notify", json={"title": "立刻", "body": "正文"}, headers=AUTH
    )

    response = await client.get("/messages", headers=AUTH)

    assert response.status_code == 200
    messages = response.json()["messages"]
    assert [message["id"] for message in messages] == [pending_id, sent.json()["id"]]
    assert messages[0]["title"] == "稍后"
    assert messages[0]["status"] == "未发"
    assert messages[0]["channels"] == [1]
    # 对外按 Asia/Shanghai 呈现时间
    assert messages[0]["scheduled_at"] == "2026-10-13T09:00:00+08:00"
    # 库里存的仍是 UTC
    assert store.get_message(pending_id).scheduled_at == "2026-10-13T01:00:00+00:00"
    assert messages[1]["title"] == "立刻"
    assert messages[1]["status"] == "已发"


async def test_messages_shows_failure_reason_of_recent_message(
    client, store, forwarder
):
    store.add_channel("fake://broken")
    forwarder.fail_urls = {"fake://broken"}
    await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )

    response = await client.get("/messages", headers=AUTH)

    message = response.json()["messages"][0]
    assert message["status"] == "失败"
    assert message["last_error"] == "发送失败：fake://broken"
    assert message["channel_results"] == [
        {
            "channel_id": 1,
            "success": False,
            "error": "发送失败：fake://broken",
            "attempts": 4,
        }
    ]
