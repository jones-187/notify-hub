"""MCP 入口：列出与取消两个工具。

接缝是公网端口的 MCP 边界；数据库与转发层出口都由测试注入。
时间对外按 Asia/Shanghai 呈现，库里仍是 UTC。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.anyio

TZ = ZoneInfo("Asia/Shanghai")


async def test_list_messages_shows_pending_then_recently_sent_with_fields(mcp, store):
    store.add_channel("fake://one")
    pending_id = store.schedule_message(
        "稍后", "正文", [1], datetime(2026, 10, 13, 9, 0, tzinfo=TZ)
    )
    sent = await mcp.call_tool("send_message", {"title": "立刻", "body": "正文"})
    sent_id = mcp.json(sent)["id"]

    result = await mcp.call_tool("list_messages", {})

    assert result["isError"] is False
    messages = mcp.json(result)["messages"]
    assert [message["id"] for message in messages] == [pending_id, sent_id]
    # 未发的消息：编号、发送时间、标题、状态
    assert messages[0] == {
        "id": pending_id,
        "scheduled_at": "2026-10-13T09:00:00+08:00",
        "title": "稍后",
        "status": "未发",
    }
    # 最近已发的消息也在列表里
    assert messages[1]["id"] == sent_id
    assert messages[1]["title"] == "立刻"
    assert messages[1]["status"] == "已发"
    assert messages[1]["scheduled_at"].endswith("+08:00")


async def test_list_messages_shows_failure_reason_for_failed_message(
    mcp, store, forwarder
):
    store.add_channel("fake://broken")
    forwarder.fail_urls = {"fake://broken"}
    failed = await mcp.call_tool("send_message", {"title": "失败", "body": "正文"})
    failed_id = mcp.json(failed)["id"]

    result = await mcp.call_tool("list_messages", {})

    message = next(m for m in mcp.json(result)["messages"] if m["id"] == failed_id)
    assert message["status"] == "失败"
    assert message["last_error"] == "发送失败：fake://broken"


async def test_list_messages_omits_last_error_for_successful_message(mcp, store):
    # 成功的消息不带失败原因，返回形状不被撑大。
    store.add_channel("fake://one")
    sent = await mcp.call_tool("send_message", {"title": "立刻", "body": "正文"})
    sent_id = mcp.json(sent)["id"]

    result = await mcp.call_tool("list_messages", {})

    message = next(m for m in mcp.json(result)["messages"] if m["id"] == sent_id)
    assert message["status"] == "已发"
    assert "last_error" not in message


async def test_list_messages_caps_how_many_it_returns(mcp, store):
    store.add_channel("fake://one")
    for index in range(60):
        store.schedule_message(
            f"标题{index}", "正文", [1], datetime(2026, 10, 13, 9, 0, tzinfo=TZ)
        )

    result = await mcp.call_tool("list_messages", {})

    assert len(mcp.json(result)["messages"]) == 50


async def test_cancel_message_cancels_pending_message_and_keeps_the_row(
    mcp, store, forwarder
):
    store.add_channel("fake://one")
    message_id = store.schedule_message(
        "排错了", "正文", [1], datetime(2026, 10, 13, 9, 0, tzinfo=TZ)
    )

    result = await mcp.call_tool("cancel_message", {"message_id": message_id})

    assert result["isError"] is False
    assert mcp.json(result) == {"id": message_id, "status": "已取消"}
    # 取消是改状态，不是删行
    stored = store.get_message(message_id)
    assert stored is not None
    assert stored.status == "已取消"
    assert forwarder.calls == []


async def test_cancel_message_with_unknown_id_returns_error(mcp, store):
    result = await mcp.call_tool("cancel_message", {"message_id": 9999})

    assert result["isError"] is True
    assert "不存在" in mcp.text(result)


async def test_cancel_message_that_was_already_sent_returns_error(
    mcp, store, forwarder
):
    store.add_channel("fake://one")
    sent = await mcp.call_tool("send_message", {"title": "已发", "body": "正文"})
    message_id = mcp.json(sent)["id"]

    result = await mcp.call_tool("cancel_message", {"message_id": message_id})

    assert result["isError"] is True
    text = mcp.text(result)
    assert str(message_id) in text
    assert "已发" in text
    # 状态没被改动，也没静默成功
    assert store.get_message(message_id).status == "已发"


async def test_cancel_message_that_was_already_cancelled_returns_error(mcp, store):
    store.add_channel("fake://one")
    message_id = store.schedule_message(
        "排错了", "正文", [1], datetime(2026, 10, 13, 9, 0, tzinfo=TZ)
    )
    await mcp.call_tool("cancel_message", {"message_id": message_id})

    result = await mcp.call_tool("cancel_message", {"message_id": message_id})

    assert result["isError"] is True
    assert "已取消" in mcp.text(result)
    assert store.get_message(message_id).status == "已取消"


async def test_cancel_message_that_failed_returns_error(mcp, store, forwarder):
    store.add_channel("fake://one")
    forwarder.fail_urls = {"fake://one"}
    failed = await mcp.call_tool("send_message", {"title": "失败", "body": "正文"})
    message_id = mcp.json(failed)["id"]

    result = await mcp.call_tool("cancel_message", {"message_id": message_id})

    assert result["isError"] is True
    assert "失败" in mcp.text(result)
    assert store.get_message(message_id).status == "失败"
