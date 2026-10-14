"""SAS tokens for the Authorization header."""

from urllib.parse import quote

import pytest

from conftest import CONNECTION_STRING, ENDPOINT, HUB_NAME, assert_valid_sas_token, split_request
from notificationhubs_rest_python import AzureNotificationHub


def token_fields(token):
    return dict(part.split("=", 1) for part in token[len("SharedAccessSignature ") :].split("&"))


@pytest.fixture
def clock(monkeypatch):
    """A clock for the SAS tokens that only moves when the test moves it."""

    class Clock:
        now = 1_800_000_000.0

        def time(self):
            return self.now

    clock = Clock()
    monkeypatch.setattr("notificationhubs_rest_python._sas.time", clock)
    return clock


def test_token_is_valid_for_an_hour(hub, clock):
    token = hub.generate_sas_token()

    assert int(token_fields(token)["se"]) == clock.now + 3600


def test_token_is_reused_for_every_send(hub, hub_api):
    hub.send_template_notification({"message": "Hello"})
    hub.send_template_notification({"message": "Hello"})

    first, second = (split_request(call.request)[2]["Authorization"] for call in hub_api.calls)
    assert first == second


def test_token_is_renewed_five_minutes_before_it_expires(hub, clock):
    first = hub.generate_sas_token()
    expiry = int(token_fields(first)["se"])

    clock.now = expiry - 300
    assert hub.generate_sas_token() == first

    clock.now = expiry - 299
    renewed = hub.generate_sas_token()
    assert renewed != first
    assert int(token_fields(renewed)["se"]) == clock.now + 3600


def test_resource_is_lowercased_but_the_url_keeps_the_hub_name(hub_api):
    hub = AzureNotificationHub(CONNECTION_STRING, "MyHub")

    hub.send_template_notification({"message": "Hello"})

    [call] = hub_api.calls
    path, _, headers, _ = split_request(call.request)
    assert path == "/MyHub/messages/"
    # The whole encoded resource is lowercased, including the escapes, as in 1.x
    assert token_fields(headers["Authorization"])["sr"] == quote(ENDPOINT + "MyHub", safe="").lower()
    assert_valid_sas_token(headers["Authorization"], resource=ENDPOINT + "MyHub")


def test_each_hub_gets_a_token_for_its_own_resource():
    first = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)
    second = AzureNotificationHub(CONNECTION_STRING, "other-hub")

    assert_valid_sas_token(first.generate_sas_token(), resource=ENDPOINT + HUB_NAME)
    assert_valid_sas_token(second.generate_sas_token(), resource=ENDPOINT + "other-hub")
