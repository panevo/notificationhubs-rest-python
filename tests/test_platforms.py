"""Platforms that changed since 1.x: FCM v1 replaces GCM, MPNS is gone, scheduled times use UTC."""

from datetime import datetime, timedelta, timezone

import pytest

from conftest import CONNECTION_STRING, HUB_NAME, json_body, split_request
from notificationhubs_rest_python import AzureNotification, AzureNotificationHub

FCM_V1_PAYLOAD = {"message": {"notification": {"title": "Hi", "body": "Hello"}}}


@pytest.fixture
def hub():
    return AzureNotificationHub(CONNECTION_STRING, HUB_NAME)


def test_google_send_uses_fcm_v1(hub, hub_api):
    status, _ = hub.send_google_notification(False, FCM_V1_PAYLOAD, tags="news")

    assert status == 201
    [call] = hub_api.calls
    headers = split_request(call.request)[2]
    assert headers["ServiceBusNotification-Format"] == "fcmV1"
    assert headers["Content-Type"] == "application/json"
    assert json_body(call.request) == FCM_V1_PAYLOAD


def test_google_direct_send_uses_fcm_v1(hub, hub_api):
    hub.send_google_notification(True, FCM_V1_PAYLOAD, device_handle="fcm-token")

    [call] = hub_api.calls
    _, query, headers, _ = split_request(call.request)
    assert "direct" in query
    assert headers["ServiceBusNotification-Format"] == "fcmV1"
    assert headers["ServiceBusNotification-DeviceHandle"] == "fcm-token"


def test_legacy_gcm_payload_is_rejected(hub, hub_api):
    with pytest.raises(ValueError, match="FCM v1"):
        hub.send_google_notification(False, {"data": {"message": "Hello"}})

    assert len(hub_api.calls) == 0


def test_gcm_format_is_rejected():
    with pytest.raises(ValueError, match="fcmV1"):
        AzureNotification("gcm", {})


def test_windows_phone_is_no_longer_supported(hub, hub_api):
    with pytest.raises(NotImplementedError, match="MPNS"):
        hub.send_windows_phone_notification(False, "<wp:Toast/>")

    assert len(hub_api.calls) == 0


def test_scheduled_time_is_sent_in_utc(hub, hub_api):
    send_at = datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone(timedelta(hours=2)))

    hub.send_template_notification({"message": "Hello"}, scheduled_time=send_at)

    [call] = hub_api.calls
    assert split_request(call.request)[2]["ServiceBusNotification-ScheduleTime"] == "2026-10-15T08:00:00"
