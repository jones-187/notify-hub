"""内网入口的 ASGI 应用。"""

import secrets

import anyio
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from notify_hub.messaging import send_now
from notify_hub.store import message_to_dict


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

    async def messages(request):
        return JSONResponse(
            {"messages": [message_to_dict(m) for m in store.list_messages()]}
        )

    async def notify(request):
        data = await request.json()
        message_id = await send_now(
            store, forwarder, data["title"], data["body"], wait=wait
        )
        return JSONResponse({"id": message_id})

    routes = [
        Route("/healthz", healthz, methods=["GET"]),
        Route("/notify", notify, methods=["POST"]),
        Route("/messages", messages, methods=["GET"]),
    ]
    return Starlette(
        routes=routes,
        middleware=[Middleware(BearerAuthMiddleware, token=token)],
    )
