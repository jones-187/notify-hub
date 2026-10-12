"""部署产物的验收。

本机没有 Docker，所以这里只检查配置文件本身：镜像基于哪个 Python、依赖走不走
锁文件、两个端口怎么映射、数据落在哪个卷、令牌从哪来。构建镜像、起容器、真发
一条消息这三件事本机做不到，只能在 NAS 上做（见 docs/deploy.md 的“本机验证不了”一节）。
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _read(name):
    return (ROOT / name).read_text(encoding="utf-8")


def _service():
    return yaml.safe_load(_read("compose.yaml"))["services"]["notify-hub"]


def test_dockerfile_base_image_and_locked_dependencies():
    text = _read("Dockerfile")
    assert "FROM python:3.12-slim" in text
    # 依赖用 uv 管理，并利用仓库里的 uv.lock，不另起一套依赖管理。
    assert "uv sync" in text
    assert "uv.lock" in text
    assert "notify_hub.main" in text


def test_compose_maps_both_ports():
    ports = [str(port) for port in _service()["ports"]]
    assert any("8080" in port for port in ports), "缺公网 MCP 端口 8080 的映射"
    assert any("8081" in port for port in ports), "缺内网端口 8081 的映射"


def test_compose_persists_db_in_mounted_volume():
    service = _service()
    mounts = [str(volume) for volume in service["volumes"]]
    assert any(mount.endswith(":/data") for mount in mounts), "数据目录没有挂到宿主机的 /data"
    # 数据库文件必须落在挂载卷里，容器重建后数据还在。
    assert "/data/notify.db" in service["environment"]["NOTIFY_DB"]


def test_compose_healthcheck_uses_tokenless_healthz():
    healthcheck = _service()["healthcheck"]
    command = " ".join(healthcheck["test"])
    assert "/healthz" in command


def test_token_only_from_environment_without_default():
    token = _service()["environment"]["NOTIFY_TOKEN"]
    # 用 :? 让令牌缺失或为空时 compose 直接报错，不给默认值。
    assert ":?" in token
    assert "NOTIFY_TOKEN" in token


def test_env_example_ships_a_placeholder_not_a_token():
    lines = [
        line
        for line in _read(".env.example").splitlines()
        if line.startswith("NOTIFY_TOKEN=")
    ]
    assert lines == ["NOTIFY_TOKEN="], "仓库里绝不能出现真令牌，只留空占位"


def test_env_file_is_gitignored():
    assert ".env" in _read(".gitignore").splitlines()


def test_docker_context_excludes_env():
    # .env 不进构建上下文，也就不会被打进镜像。
    assert ".env" in _read(".dockerignore").splitlines()


def test_deploy_doc_covers_required_steps():
    text = _read("docs/deploy.md")
    for needle in [
        "NOTIFY_TOKEN",  # 生成令牌
        "bark://",
        "ntfy://",  # 准备并填通道地址
        "备份",  # 备份数据库文件
        "升级",  # 升级镜像
        "日志",  # 看日志
        "healthz",  # 怎么检查成不成
    ]:
        assert needle in text, f"部署文档缺步骤：{needle}"


def test_dockerfile_pins_uv_image_tag():
    # 基础镜像不能用 :latest，否则每次构建拿到的 uv 可能不同，构建不可复现。
    line = next(
        (
            line
            for line in _read("Dockerfile").splitlines()
            if "ghcr.io/astral-sh/uv" in line
        ),
        "",
    )
    assert line, "Dockerfile 里找不到 uv 镜像"
    assert ":latest" not in line, "uv 镜像必须固定版本号，不能用 :latest"


def test_compose_rotates_logs():
    # Docker 默认的 json-file 驱动不轮转，长期跑会把磁盘写满。
    logging = _service().get("logging") or {}
    assert logging.get("driver") == "json-file", "日志驱动应为 json-file"
    options = logging.get("options") or {}
    assert options.get("max-size"), "日志轮转必须配 max-size"
    assert options.get("max-file"), "日志轮转必须配 max-file"
