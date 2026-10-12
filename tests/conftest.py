import httpx
import pytest

from notify_hub.app import create_app
from notify_hub.forwarder import DeliveryResult
from notify_hub.store import Store

TOKEN = "test-token"


class FakeForwarder:
    """假的转发层出口：记录收到的内容，绝不真的发消息到手机。"""

    def __init__(self):
        self.calls = []
        self.fail_urls = set()

    def send(self, apprise_url, title, body):
        self.calls.append({"apprise_url": apprise_url, "title": title, "body": body})
        if apprise_url in self.fail_urls:
            return DeliveryResult(success=False, error=f"发送失败：{apprise_url}")
        return DeliveryResult(success=True)


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
def app(store, forwarder):
    return create_app(store=store, forwarder=forwarder, token=TOKEN)


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as c:
        yield c
