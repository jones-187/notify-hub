# notify-hub 的运行镜像：一个容器、两个端口。依赖用 uv 按仓库里的 uv.lock 装。
FROM python:3.12-slim

# uv 从官方镜像拷进来。要完全复现构建时，把 :latest 换成固定的版本号。
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 虚拟环境固定在 /app/.venv；PATH 让 CMD 里的 python 用它。
ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 先只拷依赖清单并同步依赖；之后改源码不会让这一层失效。
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再把本项目装进虚拟环境，python -m notify_hub.main 才找得到包。
COPY src ./src
RUN uv sync --frozen --no-dev

# 8080：公网端口，只挂 MCP（/mcp）。8081：内网端口，挂 /notify、/healthz、/messages。
EXPOSE 8080 8081

# 日志写到标准输出，docker logs 一处看全部。
CMD ["python", "-m", "notify_hub.main"]
