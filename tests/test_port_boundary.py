"""入口：公网端口只挂 MCP，内网端口挂 /notify、/healthz、/messages。

接缝是入口自己组出来的两个 ASGI 应用；端口边界靠“哪个应用挂在哪个端口”证明。
"""

import httpx
import pytest
from mcp_client import McpHttpClient

from notify_hub.main import INTERNAL_PORT, PUBLIC_PORT, build_servers

pytestmark = pytest.mark.anyio

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def servers(store, forwarder):
    return build_servers(
        store=store,
        forwarder=forwarder,
        token=TOKEN,
        public_port=PUBLIC_PORT,
        internal_port=INTERNAL_PORT,
    )


@pytest.fixture
async def public_http(servers):
    public_app = servers.public.config.app
    # MCP 应用的 lifespan 启动会话管理器；ASGITransport 不会自己跑 lifespan。
    async with public_app.router.lifespan_context(public_app):
        transport = httpx.ASGITransport(app=public_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://public"
        ) as http:
            yield http


@pytest.fixture
async def internal_client(servers):
    transport = httpx.ASGITransport(app=servers.internal.config.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://internal"
    ) as http:
        yield http


def test_two_listeners_on_two_different_ports(servers):
    assert servers.public.config.port == PUBLIC_PORT
    assert servers.internal.config.port == INTERNAL_PORT
    assert PUBLIC_PORT != INTERNAL_PORT


async def test_public_port_serves_mcp(public_http):
    mcp = McpHttpClient(public_http, TOKEN)
    await mcp.initialize()

    tools = await mcp.list_tools()

    assert [tool["name"] for tool in tools] == [
        "send_message",
        "schedule_message",
        "list_messages",
        "cancel_message",
    ]


async def test_public_port_does_not_serve_internal_routes(public_http):
    notify = await public_http.post(
        "/notify", json={"title": "标题", "body": "正文"}
    )
    healthz = await public_http.get("/healthz")
    messages = await public_http.get("/messages")

    assert notify.status_code == 404
    assert healthz.status_code == 404
    assert messages.status_code == 404


async def test_internal_port_does_not_serve_mcp(internal_client):
    response = await internal_client.post(
        "/mcp",
        headers=AUTH,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )

    assert response.status_code == 404


async def test_internal_port_serves_healthz_notify_and_messages(
    internal_client, store, forwarder
):
    store.add_channel("fake://one")

    healthz = await internal_client.get("/healthz")
    notify = await internal_client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )
    messages = await internal_client.get("/messages", headers=AUTH)

    assert healthz.status_code == 200
    assert notify.status_code == 200
    assert forwarder.calls == [
        {"apprise_url": "fake://one", "title": "标题", "body": "正文"}
    ]
    assert [m["id"] for m in messages.json()["messages"]] == [notify.json()["id"]]
