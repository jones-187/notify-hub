"""排期层的数据存储：单个 SQLite 文件。"""

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

STATUS_PENDING = "未发"
STATUS_SENT = "已发"
STATUS_FAILED = "失败"
STATUS_CANCELLED = "已取消"


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


class Store:
    def __init__(self, path):
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
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

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
            " channels, scheduled_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def schedule_message(self, title, body, channel_ids, scheduled_at, *, now=None):
        """排一条未来时间的消息，状态为“未发”。"""
        created_at = format_utc(now if now is not None else utc_now())
        scheduled_text = format_utc(scheduled_at)
        cur = self._conn.execute(
            "INSERT INTO messages"
            " (title, body, status, channel_results, attempts, last_error,"
            " channels, scheduled_at, created_at)"
            " VALUES (?, ?, ?, '[]', 0, NULL, ?, ?, ?)",
            (
                title,
                body,
                STATUS_PENDING,
                json.dumps(list(dict.fromkeys(channel_ids))),
                scheduled_text,
                created_at,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

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
        )
