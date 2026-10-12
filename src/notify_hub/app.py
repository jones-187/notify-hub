"""内网入口的 ASGI 应用。"""

import secrets

import anyio
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route

from notify_hub.messaging import send_now
from notify_hub.paths import normalize_prefix
from notify_hub.priority import normalize_priority
from notify_hub.store import message_to_dict


class BearerAuthMiddleware:
    """校验 bearer 令牌；健康检查免令牌。"""

    def __init__(self, app, token, healthz_path="/healthz"):
        self.app = app
        self.token = token
        self.healthz_path = healthz_path

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope["path"] == self.healthz_path:
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        if not (auth.startswith("Bearer ") and secrets.compare_digest(auth[7:], self.token)):
            response = PlainTextResponse("unauthorized", status_code=401)
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def create_app(*, store, forwarder, token, path_prefix="", wait=anyio.sleep):
    """构建内网端口的应用。

    store：排期层的数据存储。
    forwarder：转发层出口。
    token：bearer 令牌。
    prefix：路径前缀（见 paths.normalize_prefix）。空则路径就是 /notify 等。
    wait：重试等待函数，测试注入假的以避免真等。

    请求体除 title / body 外可以带 priority 指定优先级
    （low / normal / high / urgent，默认 normal），见 priority 模块。
    """
    prefix = normalize_prefix(path_prefix)
    healthz_path = f"{prefix}/healthz"

    async def healthz(request):
        return PlainTextResponse("ok")

    async def messages(request):
        return JSONResponse(
            {"messages": [message_to_dict(m) for m in store.list_messages()]}
        )

    async def notify(request):
        data = await request.json()
        try:
            priority = normalize_priority(data.get("priority"))
        except ValueError as error:
            return JSONResponse({"error": str(error)}, status_code=400)
        message_id = await send_now(
            store,
            forwarder,
            data["title"],
            data["body"],
            priority=priority,
            wait=wait,
        )
        return JSONResponse({"id": message_id})

    routes = [
        Route(healthz_path, healthz, methods=["GET"]),
        Route(f"{prefix}/notify", notify, methods=["POST"]),
        Route(f"{prefix}/messages", messages, methods=["GET"]),
    ]
    return Starlette(
        routes=routes,
        middleware=[
            Middleware(
                BearerAuthMiddleware, token=token, healthz_path=healthz_path
            )
        ],
    )
