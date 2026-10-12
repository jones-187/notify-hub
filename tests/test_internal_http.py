import pytest

pytestmark = pytest.mark.anyio

AUTH = {"Authorization": "Bearer test-token"}


async def test_healthz_returns_ok_without_token(client):
    resp = await client.get("/healthz")

    assert resp.status_code == 200
    assert resp.text == "ok"


async def test_notify_without_token_returns_401(client):
    resp = await client.post("/notify", json={"title": "标题", "body": "正文"})

    assert resp.status_code == 401


async def test_notify_with_wrong_token_returns_401(client):
    resp = await client.post(
        "/notify",
        json={"title": "标题", "body": "正文"},
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert resp.status_code == 401


async def test_notify_sends_to_channel_and_returns_message_id(client, store, forwarder):
    store.add_channel("fake://channel-one")

    resp = await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )

    assert resp.status_code == 200
    assert isinstance(resp.json()["id"], int)
    assert forwarder.calls == [
        {"apprise_url": "fake://channel-one", "title": "标题", "body": "正文"}
    ]


async def test_notify_sends_to_all_enabled_channels_and_records_results(
    client, store, forwarder
):
    store.add_channel("fake://enabled-one")
    store.add_channel("fake://disabled", enabled=False)
    store.add_channel("fake://enabled-two")

    resp = await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )
    message_id = resp.json()["id"]

    assert [call["apprise_url"] for call in forwarder.calls] == [
        "fake://enabled-one",
        "fake://enabled-two",
    ]
    stored = store.get_message(message_id)
    assert stored.status == "已发"
    assert stored.channel_results == [
        {"channel_id": 1, "success": True, "error": None},
        {"channel_id": 3, "success": True, "error": None},
    ]


async def test_notify_records_failed_channel_and_still_delivers_others(
    client, store, forwarder
):
    store.add_channel("fake://ok")
    store.add_channel("fake://broken")
    forwarder.fail_urls = {"fake://broken"}

    resp = await client.post(
        "/notify", json={"title": "标题", "body": "正文"}, headers=AUTH
    )
    message_id = resp.json()["id"]

    assert [call["apprise_url"] for call in forwarder.calls] == [
        "fake://ok",
        "fake://broken",
    ]
    stored = store.get_message(message_id)
    assert stored.status == "失败"
    assert stored.channel_results == [
        {"channel_id": 1, "success": True, "error": None},
        {"channel_id": 2, "success": False, "error": "发送失败：fake://broken"},
    ]
