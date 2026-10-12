"""MCP 入口：立刻发送与排期两个工具。

接缝是公网端口的 MCP 边界；转发层出口、时钟与等待都由测试注入。
"""

import pytest
from mcp_client import INITIALIZE_PARAMS

pytestmark = pytest.mark.anyio

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def initialize_request(*, token=None):
    headers = dict(MCP_HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return headers, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": INITIALIZE_PARAMS,
    }


async def test_mcp_without_token_returns_401(mcp_http):
    headers, body = initialize_request()

    response = await mcp_http.post("/mcp", headers=headers, json=body)

    assert response.status_code == 401


async def test_mcp_with_wrong_token_returns_401(mcp_http):
    headers, body = initialize_request(token="wrong-token")

    response = await mcp_http.post("/mcp", headers=headers, json=body)

    assert response.status_code == 401


async def test_mcp_advertises_all_tools_with_parameters_explained(mcp):
    tools = {tool["name"]: tool for tool in await mcp.list_tools()}

    assert list(tools) == [
        "send_message",
        "schedule_message",
        "list_messages",
        "cancel_message",
    ]
    for tool in tools.values():
        assert tool["description"]
        for name, prop in tool["inputSchema"]["properties"].items():
            assert prop["description"], f"{tool['name']}.{name} 没有说明"

    scheduled_at = tools["schedule_message"]["inputSchema"]["properties"][
        "scheduled_at"
    ]
    assert "RFC3339" in scheduled_at["description"]
    assert "2026-10-13T08:00:00+08:00" in scheduled_at["description"]
    assert "Asia/Shanghai" in scheduled_at["description"]
    assert "过去" in scheduled_at["description"]


async def test_send_message_sends_immediately_and_returns_message_id(
    mcp, store, forwarder
):
    store.add_channel("fake://one")

    result = await mcp.call_tool("send_message", {"title": "标题", "body": "正文"})

    assert result["isError"] is False
    message_id = mcp.json(result)["id"]
    assert forwarder.calls == [
        {"apprise_url": "fake://one", "title": "标题", "body": "正文"}
    ]
    stored = store.get_message(message_id)
    assert stored.title == "标题"
    assert stored.body == "正文"
    assert stored.status == "已发"


async def test_send_message_without_enabled_channels_fails_and_records_reason(
    mcp, store, forwarder
):
    # 一条通道都没启用：其实一条也没发出去，绝不能标成“已发”。
    result = await mcp.call_tool("send_message", {"title": "标题", "body": "正文"})

    assert result["isError"] is False
    message_id = mcp.json(result)["id"]
    assert forwarder.calls == []
    stored = store.get_message(message_id)
    assert stored.status == "失败"
    assert stored.attempts == 0
    assert stored.last_error == "没有启用中的通道"


async def test_schedule_message_queues_future_message_with_absolute_time(mcp, store, forwarder):
    store.add_channel("fake://one")

    result = await mcp.call_tool(
        "schedule_message",
        {
            "title": "交燃气费",
            "body": "记得交燃气费",
            "scheduled_at": "2026-10-13T09:30:00+08:00",
        },
    )

    assert result["isError"] is False
    message_id = mcp.json(result)["id"]
    # 还没到点，一条也不发
    assert forwarder.calls == []
    stored = store.get_message(message_id)
    assert stored.title == "交燃气费"
    assert stored.body == "记得交燃气费"
    assert stored.status == "未发"
    assert stored.channels == [1]
    # 库里存 UTC
    assert stored.scheduled_at == "2026-10-13T01:30:00+00:00"
    # 回显按固定时区 Asia/Shanghai
    assert mcp.json(result)["scheduled_at"] == "2026-10-13T09:30:00+08:00"


async def test_schedule_message_normalizes_other_timezone_offsets_to_shanghai(
    mcp, store
):
    store.add_channel("fake://one")

    result = await mcp.call_tool(
        "schedule_message",
        {
            "title": "标题",
            "body": "正文",
            "scheduled_at": "2026-10-13T01:30:00+00:00",
        },
    )

    message_id = mcp.json(result)["id"]
    assert store.get_message(message_id).scheduled_at == "2026-10-13T01:30:00+00:00"
    assert mcp.json(result)["scheduled_at"] == "2026-10-13T09:30:00+08:00"


async def test_schedule_message_in_the_past_returns_error_and_schedules_nothing(
    mcp, store, forwarder
):
    store.add_channel("fake://one")

    result = await mcp.call_tool(
        "schedule_message",
        {
            "title": "标题",
            "body": "正文",
            "scheduled_at": "2026-10-13T07:59:59+08:00",
        },
    )

    assert result["isError"] is True
    text = mcp.text(result)
    # 明确报出错的发送时间和当前时间，不静默改成“现在发”
    assert "2026-10-13T07:59:59+08:00" in text
    assert "2026-10-13T08:00:00+08:00" in text
    assert forwarder.calls == []
    assert store.list_messages() == []


async def test_schedule_message_with_unclear_time_returns_error(mcp, store):
    store.add_channel("fake://one")

    naive = await mcp.call_tool(
        "schedule_message",
        {
            "title": "标题",
            "body": "正文",
            "scheduled_at": "2026-10-13T08:00:00",
        },
    )
    prose = await mcp.call_tool(
        "schedule_message",
        {
            "title": "标题",
            "body": "正文",
            "scheduled_at": "明天早上八点",
        },
    )

    assert naive["isError"] is True
    assert "时区" in mcp.text(naive)
    assert prose["isError"] is True
    assert "RFC3339" in mcp.text(prose)
    assert store.list_messages() == []
