"""路径前缀：给反向代理预留位置。

规格要求「所有路径预留前缀（例如以后 /notify 变成 /api/notify），以后加反向代理时
服务不用改」。做法是让前缀可配：默认空（路径就是 /mcp、/notify…），以后加反代时把
PATH_PREFIX 一设，路径整体前移，服务端代码不用动。
"""


def normalize_prefix(raw):
    """把路径前缀规范成 `""` 或 `"/xxx"`（无尾斜杠）。

    `notify-hub`、`notify-hub/`、`/notify-hub/` 看起来都是“对的意思”，
    为这点写法的差异启动失败不值得，所以统一收编。
    """
    if not raw:
        return ""
    prefix = raw.strip()
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    return prefix.rstrip("/")
