"""启动入口：一次把两个端口和后台排期循环都起起来。

公网端口只挂 MCP；内网端口挂 /notify、/healthz、/messages。
两条路径都可以整体前移（PATH_PREFIX），给以后加反向代理预留位置。
端口边界靠两个端口各挂一个 ASGI 应用做实，不只靠路径约定。
"""

import asyncio
import contextlib
import os
from dataclasses import dataclass

import uvicorn

from notify_hub.app import create_app
from notify_hub.forwarder import AppriseForwarder
from notify_hub.mcp_app import create_public_app
from notify_hub.paths import normalize_prefix
from notify_hub.scheduler import run_loop
from notify_hub.store import Store

PUBLIC_PORT = 8080
INTERNAL_PORT = 8081
DB_PATH = "/data/notify.db"


@dataclass(frozen=True)
class Listeners:
    """入口起的两个监听。公网那条只挂 MCP，内网那条挂普通 HTTP 接口。"""

    public: uvicorn.Server
    internal: uvicorn.Server


def config_from_env():
    """从环境变量读运行配置；令牌只从环境变量读，缺失就启动失败。"""
    return {
        "token": os.environ["NOTIFY_TOKEN"],
        "db_path": os.environ.get("NOTIFY_DB", DB_PATH),
        "public_port": int(os.environ.get("MCP_PORT", PUBLIC_PORT)),
        "internal_port": int(os.environ.get("INTERNAL_PORT", INTERNAL_PORT)),
        "path_prefix": normalize_prefix(os.environ.get("PATH_PREFIX", "")),
    }


def build_servers(
    *, store, forwarder, token, public_port, internal_port, path_prefix=""
):
    """组出两个监听：公网端口的应用只挂 MCP，内网端口的应用挂普通 HTTP 接口。"""
    public_app = create_public_app(
        store=store, forwarder=forwarder, token=token, path_prefix=path_prefix
    )
    internal_app = create_app(
        store=store, forwarder=forwarder, token=token, path_prefix=path_prefix
    )
    return Listeners(
        public=uvicorn.Server(
            uvicorn.Config(
                public_app, host="0.0.0.0", port=public_port, log_level="info"
            )
        ),
        internal=uvicorn.Server(
            uvicorn.Config(
                internal_app, host="0.0.0.0", port=internal_port, log_level="info"
            )
        ),
    )


async def serve(
    *, store, forwarder, token, public_port, internal_port, path_prefix=""
):
    """两个端口共用一条事件循环，后台排期循环也跑在这条循环上，直到收到停止信号。"""
    listeners = build_servers(
        store=store,
        forwarder=forwarder,
        token=token,
        public_port=public_port,
        internal_port=internal_port,
        path_prefix=path_prefix,
    )
    serving = [
        asyncio.create_task(listeners.public.serve()),
        asyncio.create_task(listeners.internal.serve()),
    ]
    scheduler = asyncio.create_task(run_loop(store, forwarder))
    print(
        f"notify-hub 已启动：公网端口 {public_port}（{path_prefix}/mcp），"
        f"内网端口 {internal_port}（{path_prefix}/notify、{path_prefix}/healthz、"
        f"{path_prefix}/messages）",
        flush=True,
    )
    try:
        # 任一端口退出（含收到 SIGTERM）就让两个端口一起停。
        await asyncio.wait(serving, return_when=asyncio.FIRST_COMPLETED)
    finally:
        listeners.public.should_exit = True
        listeners.internal.should_exit = True
        scheduler.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler
    # 端口起不来等启动错误在这里抛出来，进程以非零码退出。
    await asyncio.gather(*serving)


def main():
    config = config_from_env()
    store = Store(config["db_path"])
    forwarder = AppriseForwarder()
    asyncio.run(
        serve(
            store=store,
            forwarder=forwarder,
            token=config["token"],
            public_port=config["public_port"],
            internal_port=config["internal_port"],
            path_prefix=config["path_prefix"],
        )
    )


if __name__ == "__main__":
    main()
