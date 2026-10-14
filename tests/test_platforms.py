"""Platforms that changed since 1.x: FCM v1 replaces GCM, MPNS is gone, scheduled times use UTC."""

import time
from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from conftest import json_body, split_request
from notificationhubs_rest_python import AzureNotification

FCM_V1_PAYLOAD = {"message": {"notification": {"title": "Hi", "body": "Hello"}}}


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


@pytest.mark.parametrize(
    "payload",
    [
        "\ufeff<toast/>",
        '<?xml version="1.0" encoding="utf-8"?>\n<!-- Order shipped -->\n<toast launch="order"/>',
        "<!DOCTYPE toast>\n<toast/>",
    ],
)
def test_windows_type_is_set_after_the_xml_prolog(hub, hub_api, payload):
    hub.send_windows_notification(False, payload)

    [call] = hub_api.calls
    assert split_request(call.request)[2]["X-WNS-Type"] == "wns/toast"


class NoUtcOffset(tzinfo):
    """A time zone without a UTC offset. Python treats times in it as naive."""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None


@pytest.fixture
def local_time_zone():
    """Make the local time zone 5 hours behind UTC during the test."""
    if not hasattr(time, "tzset"):
        pytest.skip("Changing the local time zone needs time.tzset")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("TZ", "EST+5")
        time.tzset()
        yield
    time.tzset()


@pytest.mark.usefixtures("local_time_zone")
@pytest.mark.parametrize("time_zone", [None, NoUtcOffset()], ids=["naive", "no UTC offset"])
def test_scheduled_time_without_a_utc_offset_is_taken_as_utc(hub, hub_api, time_zone):
    send_at = datetime(2026, 10, 15, 8, 0, 0, tzinfo=time_zone)

    hub.send_template_notification({"message": "Hello"}, scheduled_time=send_at)

    [call] = hub_api.calls
    assert split_request(call.request)[2]["ServiceBusNotification-ScheduleTime"] == "2026-10-15T08:00:00"


def test_scheduled_time_is_sent_in_utc(hub, hub_api):
    send_at = datetime(2026, 10, 15, 10, 0, 0, tzinfo=timezone(timedelta(hours=2)))

    hub.send_template_notification({"message": "Hello"}, scheduled_time=send_at)

    [call] = hub_api.calls
    assert split_request(call.request)[2]["ServiceBusNotification-ScheduleTime"] == "2026-10-15T08:00:00"


@pytest.mark.parametrize(
    "payload",
    [{"message": "Hello"}, {"notification": {"body": "Hello"}}, '{"message": {}}', None, [{"message": {}}]],
)
def test_google_payload_must_be_an_fcm_v1_message(hub, hub_api, payload):
    with pytest.raises(ValueError, match="FCM v1"):
        hub.send_google_notification(False, payload)

    assert len(hub_api.calls) == 0


def test_google_data_message(hub, hub_api):
    payload = {"message": {"data": {"order": "1234"}}}

    hub.send_google_notification(False, payload)

    [call] = hub_api.calls
    assert json_body(call.request) == payload


def test_windows_phone_format_is_rejected():
    with pytest.raises(ValueError, match="MPNS"):
        AzureNotification("windowsphone", "<wp:Notification/>")


@pytest.mark.parametrize(
    ("send_at", "header"),
    [
        (datetime(2026, 10, 15, 8, 0, 0, 999999), "2026-10-15T08:00:00"),
        (datetime(2026, 10, 15, 1, 30, tzinfo=timezone(timedelta(hours=2))), "2026-10-14T23:30:00"),
        (datetime(2026, 10, 15, 20, 0, tzinfo=timezone(timedelta(hours=-6))), "2026-10-16T02:00:00"),
        (datetime(2026, 10, 15, 8, 0, tzinfo=timezone.utc), "2026-10-15T08:00:00"),
    ],
)
def test_scheduled_time_header(hub, hub_api, send_at, header):
    hub.send_template_notification({"message": "Hello"}, scheduled_time=send_at)

    [call] = hub_api.calls
    assert split_request(call.request)[2]["ServiceBusNotification-ScheduleTime"] == header
