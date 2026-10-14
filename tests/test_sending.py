"""What the send methods put on the wire, for each platform."""

import pytest

from conftest import CONNECTION_STRING, HUB_NAME, assert_valid_sas_token, json_body, split_request
from notificationhubs_rest_python.NotificationHub import AzureNotification, AzureNotificationHub

TOAST = '<toast><visual><binding template="ToastText01"><text id="1">Hi</text></binding></visual></toast>'
TILE = '<tile><visual><binding template="TileSmall"><text>Hi</text></binding></visual></tile>'
WP_TOAST = '<wp:Notification xmlns:wp="WPNotification"><wp:Toast><wp:Text1>Hi</wp:Text1></wp:Toast></wp:Notification>'
WP_TILE = '<wp:Notification xmlns:wp="WPNotification"><wp:Tile><wp:Title>Hi</wp:Title></wp:Tile></wp:Notification>'


@pytest.fixture
def hub():
    return AzureNotificationHub(CONNECTION_STRING, HUB_NAME)


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


def test_tag_set_is_sent_as_an_or_expression(hub, hub_api):
    hub.send_template_notification({"message": "Hello"}, tags={"news", "sports"})

    [call] = hub_api.calls
    tags = split_request(call.request)[2]["ServiceBusNotification-Tags"]
    assert set(tags.split(" || ")) == {"news", "sports"}


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


def test_direct_send(hub, hub_api):
    hub.send_apple_notification(True, {"aps": {"alert": "Hello"}}, device_handle="device-token")

    [call] = hub_api.calls
    path, query, headers, _ = split_request(call.request)
    assert path == "/hub/messages/"
    assert "direct" in query
    assert headers["ServiceBusNotification-DeviceHandle"] == "device-token"


def test_direct_send_without_device_handle_raises(hub, hub_api):
    with pytest.raises(Exception, match="Missing PNS device handle"):
        hub.send_apple_notification(True, {"aps": {"alert": "Hello"}})

    assert len(hub_api.calls) == 0


@pytest.mark.parametrize(
    ("method", "platform_format"),
    [
        ("send_amazon_notification", "adm"),
        ("send_baidu_notification", "baidu"),
        ("send_google_notification", "gcm"),
    ],
)
def test_other_json_platforms(hub, hub_api, method, platform_format):
    getattr(hub, method)(False, {"data": {"message": "Hello"}}, tags="news")

    [call] = hub_api.calls
    headers = split_request(call.request)[2]
    assert headers["ServiceBusNotification-Format"] == platform_format
    assert headers["Content-Type"] == "application/json"
    assert json_body(call.request) == {"data": {"message": "Hello"}}


@pytest.mark.parametrize(
    ("payload", "wns_type"),
    [(TOAST, "wns/toast"), (TILE, "wns/tile")],
)
def test_windows_send(hub, hub_api, payload, wns_type):
    hub.send_windows_notification(False, payload, tags="news")

    [call] = hub_api.calls
    _, _, headers, body = split_request(call.request)
    assert headers["ServiceBusNotification-Format"] == "windows"
    assert headers["Content-Type"] == "application/xml"
    assert headers["X-WNS-Type"] == wns_type
    assert body == payload


@pytest.mark.parametrize(
    ("payload", "target", "notification_class"),
    [(WP_TOAST, "toast", "2"), (WP_TILE, "tile", "1"), ("Hello", None, None)],
)
def test_windows_phone_send(hub, hub_api, payload, target, notification_class):
    hub.send_windows_phone_notification(False, payload, tags="news")

    [call] = hub_api.calls
    _, _, headers, body = split_request(call.request)
    assert headers["ServiceBusNotification-Format"] == "windowsphone"
    assert headers["Content-Type"] == "application/xml"
    assert headers.get("X-WindowsPhone-Target") == target
    assert headers.get("X-NotificationClass") == notification_class
    assert body == payload


def test_scheduled_send_goes_to_scheduled_notifications(hub, hub_api):
    from datetime import datetime

    hub.send_template_notification({"message": "Hello"}, scheduled_time=datetime(2026, 10, 15, 8, 0, 0))

    [call] = hub_api.calls
    path, _, headers, _ = split_request(call.request)
    assert path == "/hub/schedulednotifications/"
    assert "ServiceBusNotification-ScheduleTime" in headers


def test_skip_send_makes_no_request(hub, hub_api):
    status, headers = hub.send_template_notification({"message": "Hello"}, tags="news", skip_send=True)

    assert status == 201
    assert headers["ServiceBusNotification-Format"] == "template"
    assert len(hub_api.calls) == 0


def test_debug_sends_a_test_notification_and_prints_it(hub_api, capsys):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, debug=1)

    status, _ = hub.send_template_notification({"message": "Hello"})

    assert status == 201
    [call] = hub_api.calls
    assert split_request(call.request)[1] == {"api-version": ["2015-04"], "test": [""]}
    output = capsys.readouterr().out
    assert "--- REQUEST ---" in output
    assert "--- RESPONSE ---" in output


def test_failed_send_raises(hub, failing_hub_api):
    with pytest.raises(Exception, match="Error sending notification") as error:
        hub.send_template_notification({"message": "Hello"})

    assert "400" in str(error.value)


def test_unknown_notification_format_raises():
    with pytest.raises(Exception, match="Invalid Notification format"):
        AzureNotification("unknown", {})
