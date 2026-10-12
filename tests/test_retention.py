"""保留清理：数据库超上限时删最旧的已发/已取消消息并回收空间；未发消息永不删。

接缝是 Store 的公开清理接口。测试用很小的阈值，绝不造 10 MB 数据；
未发消息的存活用一个很久以前的未发消息来证明，绝不真等时间。
"""

import os
from datetime import datetime, timezone

from notify_hub.forwarder import ChannelDelivery
from notify_hub.store import STATUS_CANCELLED, STATUS_SENT, Store

# 很小的阈值：SQLite 空库约 16 KB，所以上限设在几十 KB，测试数据也就几十 KB。
MAX_BYTES = 24 * 1024
TARGET_BYTES = 20 * 1024


def fill_messages(store, count, *, status=STATUS_SENT, body="正文"):
    """造 count 条已尝试发送的消息，返回编号列表。"""
    ids = []
    for i in range(count):
        ids.append(
            store.add_message(
                f"标题{i}",
                body,
                status,
                [ChannelDelivery(channel_id=1, success=True)],
            )
        )
    return ids


def schedule_old_pending(store):
    """造一条很久以前的未发消息，返回编号。"""
    long_ago = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return store.schedule_message("旧提醒", "很久以前排的", [1], long_ago, now=long_ago)


def test_cleanup_deletes_oldest_sent_and_shrinks_file_below_target(tmp_path):
    db_path = tmp_path / "notify.db"
    store = Store(db_path)
    store.add_channel("fake://one")
    sent_ids = fill_messages(store, 200)
    size_before = os.path.getsize(db_path)
    assert size_before > MAX_BYTES

    deleted = store.cleanup(max_bytes=MAX_BYTES, target_bytes=TARGET_BYTES)

    size_after = os.path.getsize(db_path)
    # 删行本身不会让文件变小，必须真的回收空间
    assert size_after < size_before
    assert size_after <= TARGET_BYTES
    assert deleted > 0

    remaining = [mid for mid in sent_ids if store.get_message(mid) is not None]
    removed = [mid for mid in sent_ids if store.get_message(mid) is None]
    # 只按最旧优先：被删的都是更早的，留下的都是更晚的
    assert remaining and removed
    assert min(remaining) > max(removed)


def test_cleanup_never_deletes_pending_message_and_leaves_it_unchanged(tmp_path):
    db_path = tmp_path / "notify.db"
    store = Store(db_path)
    store.add_channel("fake://one")
    # 先造一条很久以前的未发消息，再造足够多的已发消息让文件超上限
    pending_id = schedule_old_pending(store)
    pending_before = store.get_message(pending_id)
    fill_messages(store, 200)
    assert os.path.getsize(db_path) > MAX_BYTES

    store.cleanup(max_bytes=MAX_BYTES, target_bytes=TARGET_BYTES)

    pending_after = store.get_message(pending_id)
    assert pending_after is not None
    # 内容与时间原样，一个字都不变
    assert pending_after == pending_before


def test_cleanup_deletes_oldest_cancelled_messages_too(tmp_path):
    db_path = tmp_path / "notify.db"
    store = Store(db_path)
    store.add_channel("fake://one")
    cancelled_ids = fill_messages(store, 200, status=STATUS_CANCELLED)
    pending_id = schedule_old_pending(store)
    size_before = os.path.getsize(db_path)
    assert size_before > MAX_BYTES

    deleted = store.cleanup(max_bytes=MAX_BYTES, target_bytes=TARGET_BYTES)

    assert deleted > 0
    assert os.path.getsize(db_path) < size_before
    assert os.path.getsize(db_path) <= TARGET_BYTES
    remaining = [mid for mid in cancelled_ids if store.get_message(mid) is not None]
    removed = [mid for mid in cancelled_ids if store.get_message(mid) is None]
    assert remaining and removed
    assert min(remaining) > max(removed)
    # 未发消息仍然不是候选
    assert store.get_message(pending_id) is not None


def test_cleanup_does_nothing_when_file_is_under_limit(tmp_path):
    db_path = tmp_path / "notify.db"
    store = Store(db_path)
    store.add_channel("fake://one")
    sent_ids = fill_messages(store, 3)
    pending_id = schedule_old_pending(store)
    size_before = os.path.getsize(db_path)
    assert size_before <= MAX_BYTES

    deleted = store.cleanup(max_bytes=MAX_BYTES, target_bytes=TARGET_BYTES)

    assert deleted == 0
    assert os.path.getsize(db_path) == size_before
    assert store.get_message(pending_id) is not None
    for message_id in sent_ids:
        assert store.get_message(message_id) is not None
