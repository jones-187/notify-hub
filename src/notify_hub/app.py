"""内网入口的 ASGI 应用。"""

import secrets

import anyio
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from notify_hub.forwarder import deliver
from notify_hub.store import STATUS_FAILED, STATUS_SENT


class BearerAuthMiddleware:
    """校验 bearer 令牌；健康检查免令牌。"""

    def __init__(self, app, token):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] == "/healthz":
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        if not (auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], self.token)):
            response = PlainTextResponse("unauthorized", status_code=401)
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def create_app(*, store, forwarder, token, wait=anyio.sleep):
    """构建内网端口的应用。

    store：排期层的数据存储。
    forwarder：转发层出口。
    token：bearer 令牌。
    wait：重试等待函数，测试注入假的以避免真等。
    """

    async def healthz(request):
        return PlainTextResponse("ok")

    async def notify(request):
        data = await request.json()
        channels = store.list_enabled_channels()
        deliveries = await deliver(
            forwarder, channels, data["title"], data["body"], wait=wait
        )
        status = STATUS_SENT if all(d.success for d in deliveries) else STATUS_FAILED
        attempts = max((d.attempts for d in deliveries), default=0)
        last_error = next((d.error for d in reversed(deliveries) if not d.success), None)
        message_id = store.add_message(
            data["title"],
            data["body"],
            status,
            deliveries,
            attempts=attempts,
            last_error=last_error,
        )
        return JSONResponse({"id": message_id})

    routes = [
        Route("/healthz", healthz, methods=["GET"]),
        Route("/notify", notify, methods=["POST"]),
    ]
    return Starlette(
        routes=routes,
        middleware=[Middleware(BearerAuthMiddleware, token=token)],
    )
