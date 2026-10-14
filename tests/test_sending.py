"""What the send methods put on the wire, for each platform."""

import logging
from datetime import datetime

import pytest
import responses

from conftest import ANY_HUB_URL, CONNECTION_STRING, HUB_NAME, assert_valid_sas_token, json_body, split_request
from notificationhubs_rest_python import AzureNotificationHub, NotificationHubError
from notificationhubs_rest_python.NotificationHub import AzureNotification

TOAST = '<toast><visual><binding template="ToastText01"><text id="1">Hi</text></binding></visual></toast>'
TILE = '<tile><visual><binding template="TileSmall"><text>Hi</text></binding></visual></tile>'

# Each native send method, with a payload in the format of its platform
NATIVE_SENDS = [
    ("send_apple_notification", {"aps": {"alert": "Hello"}}, "apple"),
    ("send_google_notification", {"message": {"notification": {"body": "Hello"}}}, "fcmV1"),
    ("send_amazon_notification", {"data": {"message": "Hello"}}, "adm"),
    ("send_baidu_notification", {"title": "Hello", "description": "Hello"}, "baidu"),
    ("send_windows_notification", TOAST, "windows"),
]


def test_template_send_without_tags(hub, hub_api):
    status, _ = hub.send_template_notification({"message": "Hello"})

    assert status == 201
    [call] = hub_api.calls
    path, _, headers, _ = split_request(call.request)
    assert path == "/hub/messages/"
    assert headers["Content-Type"] == "application/json"
    assert "ServiceBusNotification-Tags" not in headers
    assert json_body(call.request) == {"message": "Hello"}


def test_template_send_with_tag_expression(hub, hub_api):
    tags = "alerts && tenant:1 && site:2"

    status, _ = hub.send_template_notification(properties={"site_name": "Plant 1"}, tags=tags, skip_send=False)

    assert status == 201
    [call] = hub_api.calls
    path, query, headers, _ = split_request(call.request)
    assert path == "/hub/messages/"
    assert "api-version" in query
    assert "direct" not in query
    assert headers["ServiceBusNotification-Format"] == "template"
    assert headers["ServiceBusNotification-Tags"] == tags
    assert json_body(call.request) == {"site_name": "Plant 1"}
    assert_valid_sas_token(headers["Authorization"])


@pytest.mark.parametrize("tags", [{"sports", "news"}, frozenset({"sports", "news"})])
def test_tag_set_is_sent_as_an_or_expression(hub, hub_api, tags):
    hub.send_template_notification({"message": "Hello"}, tags=tags)

    [call] = hub_api.calls
    assert split_request(call.request)[2]["ServiceBusNotification-Tags"] == "news || sports"


@pytest.mark.parametrize("tags", ["", None])
def test_no_tags_sends_to_all_devices(hub, hub_api, tags):
    hub.send_template_notification({"message": "Hello"}, tags=tags)

    [call] = hub_api.calls
    assert "ServiceBusNotification-Tags" not in split_request(call.request)[2]


@pytest.mark.parametrize("tags", [set(), frozenset()])
def test_empty_tag_set_raises_instead_of_sending_to_everyone(hub, hub_api, tags):
    with pytest.raises(ValueError, match="at least one tag"):
        hub.send_template_notification({"message": "Hello"}, tags=tags)

    assert len(hub_api.calls) == 0


def test_template_payload_with_non_ascii_text(hub, hub_api):
    properties = {"site_name": "Café ☕ 東京"}

    hub.send_template_notification(properties)

    [call] = hub_api.calls
    assert call.request.body.isascii()
    assert json_body(call.request) == properties


def test_apple_send(hub, hub_api):
    payload = {"aps": {"alert": "Hello"}}

    status, _ = hub.send_apple_notification(False, payload, tags="news")

    assert status == 201
    [call] = hub_api.calls
    _, _, headers, _ = split_request(call.request)
    assert headers["ServiceBusNotification-Format"] == "apple"
    assert headers["Content-Type"] == "application/json"
    assert headers["ServiceBusNotification-Tags"] == "news"
    assert json_body(call.request) == payload
    assert_valid_sas_token(headers["Authorization"])


@pytest.mark.parametrize(
    ("method", "platform_format"),
    [("send_amazon_notification", "adm"), ("send_baidu_notification", "baidu")],
)
def test_other_json_platforms(hub, hub_api, method, platform_format):
    getattr(hub, method)(False, {"data": {"message": "Hello"}}, tags="news")

    [call] = hub_api.calls
    headers = split_request(call.request)[2]
    assert headers["ServiceBusNotification-Format"] == platform_format
    assert headers["Content-Type"] == "application/json"
    assert json_body(call.request) == {"data": {"message": "Hello"}}


@pytest.mark.parametrize(("method", "payload", "platform_format"), NATIVE_SENDS)
def test_direct_send(hub, hub_api, method, payload, platform_format):
    getattr(hub, method)(True, payload, device_handle="device-token")

    [call] = hub_api.calls
    path, query, headers, _ = split_request(call.request)
    assert path == "/hub/messages/"
    assert "direct" in query
    assert query["api-version"] == ["2020-06"]
    assert headers["ServiceBusNotification-Format"] == platform_format
    assert headers["ServiceBusNotification-DeviceHandle"] == "device-token"


@pytest.mark.parametrize(("method", "payload", "platform_format"), NATIVE_SENDS)
def test_direct_send_without_device_handle_raises(hub, hub_api, method, payload, platform_format):
    with pytest.raises(ValueError, match="Missing PNS device handle"):
        getattr(hub, method)(True, payload)

    assert len(hub_api.calls) == 0


def test_device_handle_is_only_used_for_direct_sends(hub, hub_api):
    hub.send_apple_notification(False, {"aps": {"alert": "Hello"}}, tags="news", device_handle="device-token")

    [call] = hub_api.calls
    _, query, headers, _ = split_request(call.request)
    assert "direct" not in query
    assert "ServiceBusNotification-DeviceHandle" not in headers


@pytest.mark.parametrize(
    ("payload", "wns_type"),
    [
        (TOAST, "wns/toast"),
        (TILE, "wns/tile"),
        ("<badge/>", "wns/badge"),
        ('<?xml version="1.0" encoding="utf-8"?>\n' + TOAST, "wns/toast"),
        ("\n  " + TILE, "wns/tile"),
    ],
)
def test_windows_send(hub, hub_api, payload, wns_type):
    hub.send_windows_notification(False, payload, tags="news")

    [call] = hub_api.calls
    _, _, headers, body = split_request(call.request)
    assert headers["ServiceBusNotification-Format"] == "windows"
    assert headers["Content-Type"] == "application/xml"
    assert headers["X-WNS-Type"] == wns_type
    assert body == payload


@pytest.mark.parametrize("payload", ["<toaster/>", "<tiles><tile/></tiles>", "Hello"])
def test_windows_send_without_a_known_root_element_has_no_wns_type(hub, hub_api, payload):
    hub.send_windows_notification(False, payload)

    [call] = hub_api.calls
    assert "X-WNS-Type" not in split_request(call.request)[2]


def test_windows_payload_is_sent_as_utf8(hub, hub_api):
    payload = (
        '<toast><visual><binding template="ToastText01"><text id="1">Café ☕ 東京</text></binding></visual></toast>'
    )

    hub.send_windows_notification(False, payload)

    [call] = hub_api.calls
    assert call.request.body == payload.encode("utf-8")


def test_scheduled_send_goes_to_scheduled_notifications(hub, hub_api):
    hub.send_template_notification({"message": "Hello"}, scheduled_time=datetime(2026, 10, 15, 8, 0, 0))

    [call] = hub_api.calls
    path, _, headers, _ = split_request(call.request)
    assert path == "/hub/schedulednotifications/"
    assert "ServiceBusNotification-ScheduleTime" in headers


def test_skip_send_makes_no_request(hub, hub_api):
    status, headers = hub.send_template_notification({"message": "Hello"}, tags="news", skip_send=True)

    assert status == 201
    assert headers["ServiceBusNotification-Format"] == "template"
    assert headers["ServiceBusNotification-Tags"] == "news"
    assert headers["Authorization"] == "[redacted]"
    assert len(hub_api.calls) == 0


@pytest.mark.parametrize("debug", [1, True])
def test_debug_sends_a_test_notification(hub_api, debug):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, debug)

    hub.send_template_notification({"message": "Hello"})

    [call] = hub_api.calls
    assert "test" in split_request(call.request)[1]


def test_debug_send_logs_the_outcome(caplog):
    caplog.set_level(logging.INFO, logger="notificationhubs_rest_python")
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, debug=1)
    outcome = "<NotificationOutcome><Success>1</Success><Failure>0</Failure></NotificationOutcome>"

    with responses.RequestsMock() as mock:
        mock.add(responses.POST, ANY_HUB_URL, status=201, body=outcome)
        hub.send_template_notification({"message": "Hello"})

    [record] = [record for record in caplog.records if record.levelno == logging.INFO]
    assert outcome in record.getMessage()


def test_debug_skip_send_makes_no_request(hub_api):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, debug=1)

    status, _ = hub.send_template_notification({"message": "Hello"}, skip_send=True)

    assert status == 201
    assert len(hub_api.calls) == 0


def test_failed_send_raises(hub, failing_hub_api):
    with pytest.raises(NotificationHubError, match="Error sending notification") as error:
        hub.send_template_notification({"message": "Hello"})

    assert error.value.status_code == 400


@pytest.mark.parametrize("notification_format", ["unknown", "fcmv1", "", None])
def test_unknown_notification_format_raises(notification_format):
    with pytest.raises(ValueError, match="Invalid Notification format.*'fcmV1'"):
        AzureNotification(notification_format, {})
