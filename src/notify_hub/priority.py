"""优先级：对外只用四档，落到通道地址上时按 Apprise 协议翻译。

**为什么档位要写进通道地址**（已用真实请求验证，2026-10-13）：

- `Apprise.notify()` 不接受额外参数，传了直接 `TypeError`；
- `notify_type`（info / success / warning / failure）对 ntfy 和 bark 只用来挑图标，
  换成 `failure` 也不会让通知变紧急。

也就是说，Apprise 里优先级是**通道级**的，只能写在通道地址的查询参数上。
所以 notify-hub 在把地址交给 Apprise 之前，先把档位翻译进去。
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# 对外只用这四档，通道无关。
LEVELS = ("low", "normal", "high", "urgent")
DEFAULT_LEVEL = "normal"

# 数字别名只是让调用方好写：路由器本来就在用 ntfy 的 3/4/5。
_ALIASES = {
    "low": "low",
    "1": "low",
    "2": "low",
    "normal": "normal",
    "3": "normal",
    "high": "high",
    "4": "high",
    "urgent": "urgent",
    "5": "urgent",
}

_NTFY_VALUES = {
    "low": "low",
    "normal": "default",
    "high": "high",
    "urgent": "max",
}
_BARK_VALUES = {
    "low": "passive",
    "normal": "active",
    "high": "timeSensitive",
    "urgent": "critical",
}

# 已知协议把档位放在哪个查询参数上、各自认什么取值。
# 不在这里的协议地址原样送出：档位不生效，但消息照发。
_QUERY_PRIORITY = {
    "ntfy": ("priority", _NTFY_VALUES),
    "ntfys": ("priority", _NTFY_VALUES),
    "bark": ("level", _BARK_VALUES),
    "barks": ("level", _BARK_VALUES),
}


def normalize_priority(raw):
    """把调用方给的档位收敛成四档之一。

    没给或给了空白当普通档；给了不认识的档位就报错，
    和发送时间的处理一致：不静默猜一个档位出来。
    """
    if raw is None:
        return DEFAULT_LEVEL
    text = str(raw).strip().lower()
    if not text:
        return DEFAULT_LEVEL
    if text not in _ALIASES:
        raise ValueError(
            f"优先级不是合法的档位：{raw!r}，"
            "可用 low / normal / high / urgent，或数字 1-5"
        )
    return _ALIASES[text]


def apply_priority(apprise_url, level):
    """把档位写进通道地址；该协议没有档位这个概念时原样返回。

    地址上原本就写着的同名参数会被覆盖，以调用方给的档位为准。
    """
    level = normalize_priority(level)
    parts = urlsplit(apprise_url)
    rule = _QUERY_PRIORITY.get(parts.scheme)
    if rule is None:
        return apprise_url
    param, values = rule
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k != param
    ]
    query.append((param, values[level]))
    return urlunsplit(parts._replace(query=urlencode(query)))
