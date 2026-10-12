"""优先级：归一化、翻译到通道地址上，以及它整条链路上的去向。"""

import sqlite3

import apprise
import pytest

from notify_hub.priority import apply_priority, normalize_priority
from notify_hub.scheduler import tick
from notify_hub.store import Store

AUTH = {"Authorization": "Bearer test-token"}

# 本改动之前线上库的建表语句（messages 还没有 priority 列）。
OLD_SCHEMA = """
CREATE TABLE channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apprise_url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE messages (
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


def test_absent_or_empty_priority_falls_back_to_normal():
    for raw in (None, "", "   "):
        assert normalize_priority(raw) == "normal"


def test_priority_names_are_case_insensitive():
    assert normalize_priority("URGENT") == "urgent"
    assert normalize_priority(" High ") == "high"


@pytest.mark.parametrize(
    "raw,expected",
    [("1", "low"), ("2", "low"), ("3", "normal"), ("4", "high"), ("5", "urgent")],
)
def test_digit_aliases_map_to_levels(raw, expected):
    assert normalize_priority(raw) == expected


def test_unknown_priority_is_rejected_instead_of_guessed():
    with pytest.raises(ValueError):
        normalize_priority("紧急")


def test_ntfy_priority_lands_on_the_priority_query_parameter():
    assert (
        apply_priority("ntfy://host:8444/topic", "urgent")
        == "ntfy://host:8444/topic?priority=max"
    )
    assert (
        apply_priority("ntfy://host:8444/topic", "normal")
        == "ntfy://host:8444/topic?priority=default"
    )


def test_bark_priority_lands_on_the_level_query_parameter():
    assert (
        apply_priority("bark://api.day.app/key", "high")
        == "bark://api.day.app/key?level=timeSensitive"
    )
    assert (
        apply_priority("barks://api.day.app/key", "urgent")
        == "barks://api.day.app/key?level=critical"
    )


def test_existing_priority_on_the_url_is_overridden_by_the_caller():
    assert (
        apply_priority("ntfy://host/topic?priority=1", "urgent")
        == "ntfy://host/topic?priority=max"
    )


def test_other_query_parameters_are_preserved():
    applied = apply_priority("ntfy://host/topic?format=markdown", "high")
    assert "format=markdown" in applied
    assert "priority=high" in applied


def test_channels_without_a_priority_concept_are_left_alone():
    assert apply_priority("mailto://user:pw@example.com", "urgent") == (
        "mailto://user:pw@example.com"
    )


def test_apprise_itself_reads_the_level_back_out_of_the_address():
    """不是自己说翻译对了：交由真实 Apprise 解析出各自的档位字段。"""
    ntfy = apprise.Apprise.instantiate(apply_priority("ntfy://h/t", "urgent"))
    bark = apprise.Apprise.instantiate(apply_priority("bark://h/k", "high"))

    assert type(ntfy).__name__ == "NotifyNtfy"
    assert ntfy.priority == "max"
    assert type(bark).__name__ == "NotifyBark"
    assert bark.level == "timeSensitive"


@pytest.mark.anyio
async def test_internal_notify_carries_the_priority_to_every_channel(
    client, store, forwarder
):
    store.add_channel("fake://one")
    store.add_channel("fake://two")

    resp = await client.post(
        "/notify",
        json={"title": "标题", "body": "正文", "priority": "urgent"},
        headers=AUTH,
    )

    assert resp.status_code == 200
    assert [call["priority"] for call in forwarder.calls] == ["urgent", "urgent"]
    listed = await client.get("/messages", headers=AUTH)
    assert listed.json()["messages"][0]["priority"] == "urgent"


@pytest.mark.anyio
async def test_internal_notify_without_a_priority_sends_at_normal(
    client, store, forwarder
):
    store.add_channel("fake://one")

    resp = await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )

    assert resp.status_code == 200
    assert forwarder.calls[0]["priority"] == "normal"


@pytest.mark.anyio
async def test_internal_notify_rejects_an_unknown_priority_without_sending(
    client, store, forwarder
):
    store.add_channel("fake://one")

    resp = await client.post(
        "/notify",
        json={"title": "标题", "body": "正文", "priority": "紧急"},
        headers=AUTH,
    )

    assert resp.status_code == 400
    assert "优先级" in resp.json()["error"]
    assert forwarder.calls == []


@pytest.mark.anyio
async def test_scheduled_message_keeps_its_priority_when_it_is_sent(
    store, forwarder, now, wait
):
    store.add_channel("fake://one")
    store.schedule_message(
        "标题", "正文", [1], now, now=now, priority="high"
    )

    await tick(store, forwarder, now=lambda: now, wait=wait)

    assert forwarder.calls[0]["priority"] == "high"


def test_database_written_before_this_change_is_migrated(tmp_path):
    """线上是一个带数据的旧库：补列之后老消息要能读出来，且当普通档。"""
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO messages (title, body, status, scheduled_at, created_at)"
        " VALUES ('旧标题', '旧正文', '已发',"
        " '2026-10-12T00:00:00+00:00', '2026-10-12T00:00:00+00:00')"
    )
    conn.commit()
    conn.close()

    reopened = Store(path)

    assert reopened.get_message(1).priority == "normal"
    assert reopened.get_message(1).title == "旧标题"
