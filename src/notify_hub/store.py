"""排期层的数据存储：单个 SQLite 文件。"""

import json
import math
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from notify_hub.priority import DEFAULT_LEVEL

# 服务只用一个时区：对外的时间都按它理解、按它回显。
SHANGHAI = ZoneInfo("Asia/Shanghai")

STATUS_PENDING = "未发"
STATUS_SENT = "已发"
STATUS_FAILED = "失败"
STATUS_CANCELLED = "已取消"

# 保留上限：数据库文件超过 MAX_BYTES 时清理，降到 TARGET_BYTES 以下。
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_TARGET_BYTES = 8 * 1024 * 1024


def utc_now():
    """可注入的时钟默认实现：当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def format_utc(dt):
    """把带时区的时间转成固定格式的 UTC RFC3339 字符串。

    固定格式保证同一时区下按字符串排序等于按时间排序。
    """
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("时间必须带时区")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def format_shanghai(dt):
    """把带时区的时间转成固定格式的 Asia/Shanghai RFC3339 字符串。"""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("时间必须带时区")
    return dt.astimezone(SHANGHAI).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def parse_scheduled_at(text):
    """把对外的带时区 RFC3339 字符串解析成带时区的时间。

    不带时区或以其它格式给出时报错，不做静默猜测。
    """
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"发送时间不是合法的 RFC3339 时间：{text!r}，"
            "正确格式例如 2026-10-13T08:00:00+08:00"
        ) from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(
            f"发送时间必须带时区：{text!r}，正确格式例如 2026-10-13T08:00:00+08:00"
        )
    return dt


def message_summary(message):
    """列表里一条消息的对外形状：编号、发送时间、标题、状态。

    发送时间按 Asia/Shanghai 呈现，库里存的仍是 UTC。
    只有失败的消息才带上失败原因；成功的记录不带，不把返回形状撑大。
    """
    summary = {
        "id": message.id,
        "scheduled_at": format_shanghai(
            datetime.fromisoformat(message.scheduled_at)
        ),
        "title": message.title,
        "status": message.status,
    }
    if message.status == STATUS_FAILED:
        summary["last_error"] = message.last_error
    return summary


def message_to_dict(message):
    """消息对外的形状：时间按 Asia/Shanghai 呈现，库里存的仍是 UTC。"""
    return {
        "id": message.id,
        "title": message.title,
        "body": message.body,
        "status": message.status,
        "priority": message.priority,
        "channels": message.channels,
        "scheduled_at": format_shanghai(datetime.fromisoformat(message.scheduled_at)),
        "created_at": format_shanghai(datetime.fromisoformat(message.created_at)),
        "attempts": message.attempts,
        "last_error": message.last_error,
        "channel_results": message.channel_results,
    }


@dataclass(frozen=True)
class Channel:
    """通道表的一行。apprise_url 就是这条通道的连接地址。"""

    id: int
    apprise_url: str


@dataclass(frozen=True)
class Message:
    id: int
    title: str
    body: str
    status: str
    channel_results: list
    attempts: int = 0
    last_error: str | None = None
    channels: list = field(default_factory=list)
    scheduled_at: str | None = None
    created_at: str | None = None
    priority: str = DEFAULT_LEVEL


class Store:
    def __init__(self, path):
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self):
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apprise_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                status TEXT NOT NULL,
                channel_results TEXT NOT NULL DEFAULT '[]',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                channels TEXT NOT NULL DEFAULT '[]',
                scheduled_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                priority TEXT NOT NULL DEFAULT 'normal'
            );
            """
        )
        self._migrate()
        self._conn.commit()

    def _migrate(self):
        """给早于本版本的库补上新列；新库建表时已经带上了。"""
        columns = {
            row["name"] for row in self._conn.execute("PRAGMA table_info(messages)")
        }
        if "priority" not in columns:
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN priority TEXT NOT NULL"
                f" DEFAULT '{DEFAULT_LEVEL}'"
            )

    def add_channel(self, apprise_url, enabled=True):
        cur = self._conn.execute(
            "INSERT INTO channels (apprise_url, enabled) VALUES (?, ?)",
            (apprise_url, 1 if enabled else 0),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_enabled_channels(self):
        rows = self._conn.execute(
            "SELECT id, apprise_url FROM channels WHERE enabled = 1 ORDER BY id"
        ).fetchall()
        return [Channel(id=row["id"], apprise_url=row["apprise_url"]) for row in rows]

    def get_channels(self, channel_ids):
        """按编号取启用中的通道，保持编号顺序去重。"""
        ids = list(dict.fromkeys(channel_ids))
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._conn.execute(
            f"SELECT id, apprise_url FROM channels"
            f" WHERE enabled = 1 AND id IN ({placeholders}) ORDER BY id",
            ids,
        ).fetchall()
        return [Channel(id=row["id"], apprise_url=row["apprise_url"]) for row in rows]

    def add_message(
        self,
        title,
        body,
        status,
        channel_results,
        attempts=0,
        last_error=None,
        *,
        channels=None,
        scheduled_at=None,
        created_at=None,
        priority=DEFAULT_LEVEL,
    ):
        """记录一条已尝试发送的消息（立即发送路径）。"""
        if channels is None:
            channels = [r.channel_id for r in channel_results]
        if created_at is None:
            created_at = format_utc(utc_now())
        if scheduled_at is None:
            scheduled_at = created_at
        cur = self._conn.execute(
            "INSERT INTO messages"
            " (title, body, status, channel_results, attempts, last_error,"
            " channels, scheduled_at, created_at, priority)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                title,
                body,
                status,
                json.dumps([asdict(r) for r in channel_results]),
                attempts,
                last_error,
                json.dumps(list(dict.fromkeys(channels))),
                scheduled_at,
                created_at,
                priority,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def schedule_message(
        self,
        title,
        body,
        channel_ids,
        scheduled_at,
        *,
        now=None,
        priority=DEFAULT_LEVEL,
    ):
        """排一条未来时间的消息，状态为“未发”。"""
        created_at = format_utc(now if now is not None else utc_now())
        scheduled_text = format_utc(scheduled_at)
        cur = self._conn.execute(
            "INSERT INTO messages"
            " (title, body, status, channel_results, attempts, last_error,"
            " channels, scheduled_at, created_at, priority)"
            " VALUES (?, ?, ?, '[]', 0, NULL, ?, ?, ?, ?)",
            (
                title,
                body,
                STATUS_PENDING,
                json.dumps(list(dict.fromkeys(channel_ids))),
                scheduled_text,
                created_at,
                priority,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_messages(self, *, pending_limit=50, sent_limit=50):
        """未发的消息（发送时间由早到晚）加最近发送过的消息（由晚到早）。"""
        pending = self._conn.execute(
            "SELECT * FROM messages WHERE status = ?"
            " ORDER BY scheduled_at, id LIMIT ?",
            (STATUS_PENDING, pending_limit),
        ).fetchall()
        sent = self._conn.execute(
            "SELECT * FROM messages WHERE status IN (?, ?)"
            " ORDER BY id DESC LIMIT ?",
            (STATUS_SENT, STATUS_FAILED, sent_limit),
        ).fetchall()
        return [self._row_to_message(row) for row in list(pending) + list(sent)]

    def cancel_message(self, message_id):
        """把一条未发的消息置为“已取消”，不删行。

        返回 (message, cancelled)：message 为 None 表示编号不存在；
        cancelled 为 False 表示这条消息不在“未发”状态，没有被取消。
        """
        row = self._conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            return None, False
        cur = self._conn.execute(
            "UPDATE messages SET status = ? WHERE id = ? AND status = ?",
            (STATUS_CANCELLED, message_id, STATUS_PENDING),
        )
        self._conn.commit()
        updated = self._conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        return self._row_to_message(updated), cur.rowcount == 1

    def fetch_due_messages(self, now, limit=50):
        """取出到点仍未发的消息，最多 limit 条。"""
        due_at = format_utc(now)
        rows = self._conn.execute(
            "SELECT * FROM messages"
            " WHERE status = ? AND scheduled_at <= ?"
            " ORDER BY scheduled_at, id LIMIT ?",
            (STATUS_PENDING, due_at, limit),
        ).fetchall()
        return [self._row_to_message(row) for row in rows]

    def update_message_status(
        self, message_id, status, channel_results, attempts=0, last_error=None
    ):
        self._conn.execute(
            "UPDATE messages"
            " SET status = ?, channel_results = ?, attempts = ?, last_error = ?"
            " WHERE id = ?",
            (
                status,
                json.dumps([asdict(r) for r in channel_results]),
                attempts,
                last_error,
                message_id,
            ),
        )
        self._conn.commit()

    def cleanup(self, *, max_bytes=DEFAULT_MAX_BYTES, target_bytes=DEFAULT_TARGET_BYTES):
        """超过 max_bytes 时删最旧的已发、已取消和失败消息，回收空间到 target_bytes 以下。

        只删已发、已取消和失败的消息，未发的消息永远不是候选。
        失败的消息也是历史，不是待发的消息；通道一直坏时靠删它们才能把文件降下来。
        删除后文件不会自己变小，所以最后 VACUUM 一次真正回收空间。
        返回被删掉的消息条数。
        """
        if self._file_size() <= max_bytes:
            return 0

        deleted = 0
        while True:
            live_bytes = self._live_size()
            if live_bytes <= target_bytes:
                break
            removed = self._delete_oldest_reclaimable(live_bytes, target_bytes)
            if removed == 0:
                break
            deleted += removed

        self._conn.execute("VACUUM")
        return deleted

    def _file_size(self):
        return os.path.getsize(self._path)

    def _live_size(self):
        """VACUUM 后文件大约会收缩到的字节数：在用页数乘页大小。"""
        page_count = self._conn.execute("PRAGMA page_count").fetchone()[0]
        free_pages = self._conn.execute("PRAGMA freelist_count").fetchone()[0]
        page_size = self._conn.execute("PRAGMA page_size").fetchone()[0]
        return (page_count - free_pages) * page_size

    def _delete_oldest_reclaimable(self, live_bytes, target_bytes):
        """删最旧的一批已发/已取消/失败消息；只删到接近目标所需的数量，避免多删历史。"""
        reclaimable = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE status IN (?, ?, ?)",
            (STATUS_SENT, STATUS_CANCELLED, STATUS_FAILED),
        ).fetchone()[0]
        if reclaimable == 0:
            return 0
        total = self._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        average_row = live_bytes / total if total else 1
        needed = max(1, math.ceil((live_bytes - target_bytes) / average_row))
        batch = min(reclaimable, needed)
        rows = self._conn.execute(
            "SELECT id FROM messages WHERE status IN (?, ?, ?)"
            " ORDER BY created_at, id LIMIT ?",
            (STATUS_SENT, STATUS_CANCELLED, STATUS_FAILED, batch),
        ).fetchall()
        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" for _ in ids)
        self._conn.execute(
            f"DELETE FROM messages WHERE id IN ({placeholders})", ids
        )
        self._conn.commit()
        return len(ids)

    def get_message(self, message_id):
        row = self._conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_message(row)

    @staticmethod
    def _row_to_message(row):
        return Message(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            status=row["status"],
            channel_results=json.loads(row["channel_results"]),
            attempts=row["attempts"],
            last_error=row["last_error"],
            channels=json.loads(row["channels"] or "[]"),
            scheduled_at=row["scheduled_at"],
            created_at=row["created_at"],
            priority=row["priority"],
        )
