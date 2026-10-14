"""Bugs in the 1.x code, written as the behaviour we want.

Each test is marked as an expected failure. The change that fixes a bug removes its marker,
so the test then has to pass.
"""

from datetime import datetime

import pytest

from conftest import CONNECTION_STRING, HUB_NAME, KEY, KEY_NAME, assert_valid_sas_token, split_request
from notificationhubs_rest_python.NotificationHub import AzureNotificationHub

OTHER_CONNECTION_STRING = (
    "Endpoint=sb://other.servicebus.windows.net/;SharedAccessKeyName=OtherKeyName;SharedAccessKey=b3RoZXIta2V5"
)


@pytest.mark.xfail(strict=True, reason="1.x stores the credentials on the class, so all hubs share the last ones")
def test_each_hub_keeps_its_own_credentials(hub_api):
    first = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)
    AzureNotificationHub(OTHER_CONNECTION_STRING, "other-hub")

    first.send_template_notification({"message": "Hello"})

    [call] = hub_api.calls
    assert call.request.url.startswith("https://example.servicebus.windows.net/hub/")
    assert_valid_sas_token(split_request(call.request)[2]["Authorization"])


@pytest.mark.xfail(strict=True, reason="1.x requires exactly three parts in the connection string")
def test_connection_string_with_trailing_semicolon():
    hub = AzureNotificationHub(CONNECTION_STRING + ";", HUB_NAME)

    assert hub.Endpoint == "https://example.servicebus.windows.net/"


@pytest.mark.xfail(strict=True, reason="1.x reads the key correctly only when it comes after the key name")
def test_connection_string_parts_in_any_order(hub_api):
    connection_string = (
        "SharedAccessKey=" + KEY + ";SharedAccessKeyName=" + KEY_NAME + ";Endpoint=sb://example.servicebus.windows.net/"
    )
    hub = AzureNotificationHub(connection_string, HUB_NAME)

    hub.send_template_notification({"message": "Hello"})

    [call] = hub_api.calls
    assert_valid_sas_token(split_request(call.request)[2]["Authorization"])


@pytest.mark.xfail(strict=True, reason="1.x formats the time with literal quotes around the T")
def test_scheduled_time_header_format(hub_api):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)

    hub.send_template_notification({"message": "Hello"}, scheduled_time=datetime(2026, 10, 15, 8, 0, 0))

    [call] = hub_api.calls
    assert split_request(call.request)[2]["ServiceBusNotification-ScheduleTime"] == "2026-10-15T08:00:00"


@pytest.mark.xfail(strict=True, reason="1.x never checks the status code when debug is on")
def test_failed_debug_send_raises(failing_hub_api):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, debug=1)

    with pytest.raises(Exception, match="Error sending notification"):
        hub.send_template_notification({"message": "Hello"})


@pytest.mark.xfail(strict=True, reason="1.x sends requests without a timeout")
def test_requests_have_a_timeout(hub_api):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)

    hub.send_template_notification({"message": "Hello"})

    [call] = hub_api.calls
    assert call.request.req_kwargs.get("timeout") is not None


@pytest.mark.xfail(strict=True, reason="1.x returns the live SAS token in the headers")
def test_returned_headers_do_not_contain_the_sas_token(hub_api):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)

    _, headers = hub.send_template_notification({"message": "Hello"})

    assert not headers["Authorization"].startswith("SharedAccessSignature")


@pytest.mark.xfail(strict=True, reason="1.x only recognises <toast>, <tile> and <badge> without attributes")
@pytest.mark.parametrize(
    ("payload", "wns_type"),
    [('<badge value="1"/>', "wns/badge"), ('<toast launch="args"><visual/></toast>', "wns/toast")],
)
def test_windows_type_is_set_when_the_root_element_has_attributes(hub_api, payload, wns_type):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)

    hub.send_windows_notification(False, payload)

    [call] = hub_api.calls
    assert split_request(call.request)[2].get("X-WNS-Type") == wns_type
