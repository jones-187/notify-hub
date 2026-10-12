"""路径前缀：给反向代理预留位置。

规格要求「所有路径预留前缀（例如以后 /notify 变成 /api/notify），以后加反向代理时
服务不用改」。这里断言的是外部行为：设了前缀，前缀下的路径通、裸路径 404，
且鉴权等语义跟着搬过去；前缀写法容错。
"""

import httpx
import pytest
from mcp_client import McpHttpClient

from notify_hub.app import create_app
from notify_hub.mcp_app import create_public_app

pytestmark = pytest.mark.anyio

PREFIX = "/notify-hub"
TOKEN = "test-token"
TOOLS = {"send_message", "schedule_message", "list_messages", "cancel_message"}


@pytest.fixture
def prefixed_internal(store, forwarder, wait):
    return create_app(
        store=store,
        forwarder=forwarder,
        token=TOKEN,
        path_prefix=PREFIX,
        wait=wait,
    )


@pytest.fixture
async def prefixed_client(prefixed_internal):
    transport = httpx.ASGITransport(app=prefixed_internal)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as c:
        yield c


async def test_internal_routes_live_under_prefix(prefixed_client):
    response = await prefixed_client.get(f"{PREFIX}/healthz")
    assert response.status_code == 200
    assert response.text == "ok"

    response = await prefixed_client.post(
        f"{PREFIX}/notify",
        json={"title": "标题", "body": "正文"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200

    response = await prefixed_client.get(
        f"{PREFIX}/messages", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200


async def test_bare_paths_are_no_longer_served(prefixed_client):
    # 前缀一设，裸路径就不再提供服务，否则「预留」等于没预留：反代转发时还会撞车。
    # 内网应用的鉴权中间件在最外层，所以未带令牌时裸路径回 401 而不是 404
    # （不告诉外界哪些路径存在）；带上令牌就如实 404。
    auth = {"Authorization": f"Bearer {TOKEN}"}
    for path in ("/healthz", "/notify", "/messages"):
        tokenless = await prefixed_client.get(path)
        assert tokenless.status_code == 401, path
        with_token = await prefixed_client.get(path, headers=auth)
        assert with_token.status_code == 404, path


async def test_auth_semantics_move_with_the_prefix(prefixed_client):
    # 健康检查搬过去后依然免令牌。
    assert (await prefixed_client.get(f"{PREFIX}/healthz")).status_code == 200
    # 内网接口搬过去后依然要令牌。
    assert (await prefixed_client.get(f"{PREFIX}/messages")).status_code == 401


async def test_prefix_tolerates_common_spellings(store, forwarder, wait):
    for spelling in ("/notify-hub", "notify-hub", "/notify-hub/", "notify-hub/"):
        app = create_app(
            store=store,
            forwarder=forwarder,
            token=TOKEN,
            path_prefix=spelling,
            wait=wait,
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://internal"
        ) as c:
            response = await c.get(f"{PREFIX}/healthz")
            assert response.status_code == 200, spelling


async def test_public_mcp_lives_under_prefix(store, forwarder, wait, now):
    app = create_public_app(
        store=store,
        forwarder=forwarder,
        token=TOKEN,
        now=lambda: now,
        wait=wait,
        path_prefix=PREFIX,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://public"
        ) as http:
            # 裸 /mcp 必须消失。
            bare = await http.post(
                "/mcp",
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            )
            assert bare.status_code == 404

            # 前缀下的路径必须是完整的 MCP：初始化 + 工具都在。
            client = McpHttpClient(http, TOKEN, path=f"{PREFIX}/mcp")
            await client.initialize()
            tools = await client.list_tools()
            assert {tool["name"] for tool in tools} == TOOLS
