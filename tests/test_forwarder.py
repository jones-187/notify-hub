from notify_hub.forwarder import AppriseForwarder


def test_apprise_forwarder_reports_invalid_channel_address():
    result = AppriseForwarder().send("not a url", "标题", "正文")

    assert result.success is False
    assert result.error
