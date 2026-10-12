"""排期层的数据存储：单个 SQLite 文件。"""

import json
import sqlite3
from dataclasses import asdict, dataclass

STATUS_SENT = "已发"
STATUS_FAILED = "失败"


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
                last_error TEXT
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

    def add_message(
        self, title, body, status, channel_results, attempts=0, last_error=None
    ):
        cur = self._conn.execute(
            "INSERT INTO messages"
            " (title, body, status, channel_results, attempts, last_error)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                title,
                body,
                status,
                json.dumps([asdict(r) for r in channel_results]),
                attempts,
                last_error,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_message(self, message_id):
        row = self._conn.execute(
            "SELECT * FROM messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            return None
        return Message(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            status=row["status"],
            channel_results=json.loads(row["channel_results"]),
            attempts=row["attempts"],
            last_error=row["last_error"],
        )
