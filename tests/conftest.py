from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from mcp_client import McpHttpClient

from notify_hub.app import create_app
from notify_hub.forwarder import DeliveryResult
from notify_hub.mcp_app import create_public_app
from notify_hub.priority import DEFAULT_LEVEL
from notify_hub.store import Store

TOKEN = "test-token"
TZ = ZoneInfo("Asia/Shanghai")


class FakeForwarder:
    """假的转发层出口：记录收到的内容，绝不真的发消息到手机。"""

    def __init__(self):
        self.calls = []
        self.fail_urls = set()
        self.fail_times = {}

    def send(self, apprise_url, title, body, priority=DEFAULT_LEVEL):
        self.calls.append(
            {
                "apprise_url": apprise_url,
                "title": title,
                "body": body,
                "priority": priority,
            }
        )
        if apprise_url in self.fail_urls:
            return DeliveryResult(success=False, error=f"发送失败：{apprise_url}")
        if self.fail_times.get(apprise_url, 0) > 0:
            self.fail_times[apprise_url] -= 1
            return DeliveryResult(success=False, error=f"发送失败：{apprise_url}")
        return DeliveryResult(success=True)

    def call_counts(self):
        """每个通道被调用的次数。"""
        counts = {}
        for call in self.calls:
            counts[call["apprise_url"]] = counts.get(call["apprise_url"], 0) + 1
        return counts


class FakeWait:
    """假的重试等待：记录每次等待的时长，绝不真的等几十秒。"""

    def __init__(self):
        self.delays = []

    async def __call__(self, delay):
        self.delays.append(delay)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "notify.db")


@pytest.fixture
def forwarder():
    return FakeForwarder()


@pytest.fixture
def wait():
    return FakeWait()


@pytest.fixture
def app(store, forwarder, wait):
    return create_app(store=store, forwarder=forwarder, token=TOKEN, wait=wait)


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as c:
        yield c


@pytest.fixture
def now():
    """固定在 2026-10-13 08:00:00+08:00 的“现在”，测试从不真等。"""
    return datetime(2026, 10, 13, 8, 0, 0, tzinfo=TZ)


@pytest.fixture
def public_app(store, forwarder, wait, now):
    return create_public_app(
        store=store,
        forwarder=forwarder,
        token=TOKEN,
        now=lambda: now,
        wait=wait,
    )


@pytest.fixture
async def mcp_http(public_app):
    # MCP 应用的 lifespan 启动会话管理器；ASGITransport 不会自己跑 lifespan。
    async with public_app.router.lifespan_context(public_app):
        transport = httpx.ASGITransport(app=public_app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://public"
        ) as http:
            yield http


@pytest.fixture
async def mcp(mcp_http):
    client = McpHttpClient(mcp_http, TOKEN)
    await client.initialize()
    yield client
