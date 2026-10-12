"""公网入口的 ASGI 应用：只挂 MCP。

令牌由 SDK 自带的 token_verifier 校验；内网接口不在这里注册。
"""

import secrets
from typing import Annotated

import anyio
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from notify_hub.messaging import send_now
from notify_hub.store import (
    format_shanghai,
    message_summary,
    parse_scheduled_at,
    utc_now,
)

TITLE = Annotated[str, Field(description="消息标题，纯文本。")]
BODY = Annotated[str, Field(description="消息正文，纯文本。")]
SCHEDULED_AT = Annotated[
    str,
    Field(
        description=(
            "发送时间，必须带时区的 RFC3339 字符串，例如 "
            '\"2026-10-13T08:00:00+08:00\"（即 2026 年 10 月 13 日 上午 8 点）。'
            "时区固定按 Asia/Shanghai（UTC+8）理解，也接受其它偏移量，"
            '例如 "2026-10-13T00:00:00Z" 或 "2026-10-12T16:00:00-08:00"。'
            "不能省略时区，不能写“明天早上八点”这类自然语言。"
            "发送时间落在过去时本工具返回错误，不会改成立刻发送。"
        )
    ),
]

MESSAGE_ID = Annotated[
    int,
    Field(
        description=(
            "消息编号，来自 send_message / schedule_message 的返回，"
            "或 list_messages 里某条消息的 id。"
        )
    ),
]

# 静态共享令牌没有 OAuth 授权服务器，这两个地址只用于回 OAuth 元数据，是占位值。
ISSUER_URL = "https://notify-hub.invalid"
RESOURCE_URL = "http://127.0.0.1:8080/mcp"
SCOPE = "notify"


class StaticTokenVerifier:
    """整服务共用一个 bearer 令牌。"""

    def __init__(self, token):
        self._token = token

    async def verify_token(self, token):
        if not secrets.compare_digest(token, self._token):
            return None
        return AccessToken(token=token, client_id="notify-hub", scopes=[SCOPE])


def _parse_or_tool_error(scheduled_at):
    """时间写得不对时，把错误原文交给调用方，不猜测、不改写成“现在”。"""
    try:
        return parse_scheduled_at(scheduled_at)
    except ValueError as exc:
        raise ToolError(str(exc)) from None


def create_public_app(*, store, forwarder, token, now=utc_now, wait=anyio.sleep):
    """构建公网端口的应用。

    store：排期层的数据存储。
    forwarder：转发层出口。
    token：bearer 令牌。
    now：取“现在”的函数，测试注入假的以判断时间是否落在过去。
    wait：重试等待函数，测试注入假的以避免真等。
    """
    mcp = MCPServer(
        "notify-hub",
        token_verifier=StaticTokenVerifier(token),
        auth=AuthSettings(
            issuer_url=ISSUER_URL,
            resource_server_url=RESOURCE_URL,
            required_scopes=[SCOPE],
            validate_token_resource=False,
        ),
    )

    @mcp.tool()
    async def send_message(title: TITLE, body: BODY) -> dict:
        """立刻发送一条消息，不排期。发给所有启用中的通道。

        返回 {"id": 消息编号}。
        """
        message_id = await send_now(store, forwarder, title, body, wait=wait)
        return {"id": message_id}

    @mcp.tool()
    async def schedule_message(
        title: TITLE, body: BODY, scheduled_at: SCHEDULED_AT
    ) -> dict:
        """排期一条消息，到 scheduled_at 指定的绝对时间才发送，发给所有启用中的通道。

        排期跨度没有上限，服务重启后仍然有效。
        返回 {"id": 消息编号, "scheduled_at": 按 Asia/Shanghai 回显的发送时间}。
        """
        scheduled = _parse_or_tool_error(scheduled_at)
        current = now()
        if scheduled < current:
            raise ToolError(
                f"发送时间落在过去：{format_shanghai(scheduled)}"
                f"，当前时间：{format_shanghai(current)}"
            )
        message_id = store.schedule_message(
            title, body, [c.id for c in store.list_enabled_channels()], scheduled
        )
        return {"id": message_id, "scheduled_at": format_shanghai(scheduled)}

    @mcp.tool()
    async def list_messages() -> dict:
        """列出还没发的消息和最近已发的消息，最多各 50 条。

        每条含编号 id、发送时间（按 Asia/Shanghai 呈现）、标题、状态。
        未发的消息在前（发送时间由早到晚），最近已发的在后（由新到旧）。
        用返回的 id 可以调 cancel_message 取消一条未发的消息。
        """
        return {
            "messages": [message_summary(m) for m in store.list_messages()]
        }

    @mcp.tool()
    async def cancel_message(message_id: MESSAGE_ID) -> dict:
        """取消一条还没发出去的消息（状态变成“已取消”），返回是否成功。

        message_id 来自 send_message / schedule_message 的返回或 list_messages 的 id。
        只有“未发”的消息能取消；编号不存在，或消息已经发出、已经取消、发送失败时
        本工具返回错误，不会静默成功。取消不删行，消息仍留在列表里。
        """
        message, cancelled = store.cancel_message(message_id)
        if message is None:
            raise ToolError(f"编号 {message_id} 的消息不存在")
        if not cancelled:
            raise ToolError(
                f"编号 {message_id} 的消息状态是“{message.status}”，"
                "只有“未发”的消息才能取消"
            )
        return {"id": message.id, "status": message.status}

    return mcp.streamable_http_app(streamable_http_path="/mcp", host="0.0.0.0")
