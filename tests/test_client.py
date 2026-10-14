"""Behaviour of the 2.0 client: API version, SAS tokens, retries, errors and logging."""

import logging

import pytest
import responses
from responses.registries import OrderedRegistry

from conftest import ANY_HUB_URL, CONNECTION_STRING, HUB_NAME, assert_valid_sas_token, split_request
from notificationhubs_rest_python import AzureNotificationHub, NotificationHubError


@pytest.fixture
def hub():
    return AzureNotificationHub(CONNECTION_STRING, HUB_NAME)


@pytest.fixture
def sleeps(monkeypatch):
    """Record retry delays instead of sleeping."""
    delays = []
    monkeypatch.setattr("notificationhubs_rest_python._transport.time.sleep", delays.append)
    return delays


def sequence(*statuses, headers=None):
    """A fake API that answers each request with the next status in the list."""
    mock = responses.RequestsMock(registry=OrderedRegistry)
    for status in statuses:
        mock.add(responses.POST, ANY_HUB_URL, status=status, headers=headers if status != 201 else None)
    return mock


def test_hub_name_is_required():
    with pytest.raises(ValueError, match="hub name"):
        AzureNotificationHub(CONNECTION_STRING)


def test_uses_api_version_2020_06(hub, hub_api):
    hub.send_template_notification({"message": "Hello"})

    [call] = hub_api.calls
    _, query, headers, _ = split_request(call.request)
    assert query["api-version"] == ["2020-06"]
    assert headers["x-ms-version"] == "2020-06"


def test_public_sas_token(hub):
    assert_valid_sas_token(hub.generate_sas_token())


def test_private_sas_token_name_still_works(hub):
    assert hub._AzureNotificationHub__generate_sas_token() == hub.generate_sas_token()


def test_sas_token_is_cached_until_close_to_expiry(hub, monkeypatch):
    first = hub.generate_sas_token()
    assert hub.generate_sas_token() == first

    import notificationhubs_rest_python._sas as sas

    now = sas.time.time()
    monkeypatch.setattr(sas.time, "time", lambda: now + 3600)
    renewed = hub.generate_sas_token()
    assert renewed != first


def test_200_counts_as_success(hub):
    with sequence(200):
        status, _ = hub.send_template_notification({"message": "Hello"})

    assert status == 200


def test_throttled_send_is_retried_after_retry_after(hub, sleeps):
    with sequence(429, 201, headers={"Retry-After": "7"}) as mock:
        status, _ = hub.send_template_notification({"message": "Hello"})
        assert len(mock.calls) == 2

    assert status == 201
    assert sleeps == [7]


def test_transient_errors_are_retried_three_times(hub, sleeps):
    with sequence(503, 503, 503, 503) as mock:
        with pytest.raises(NotificationHubError) as error:
            hub.send_template_notification({"message": "Hello"})
        assert len(mock.calls) == 4

    assert len(sleeps) == 3
    assert error.value.status_code == 503


def test_retries_can_be_switched_off(sleeps):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, max_retries=0)

    with sequence(503) as mock:
        with pytest.raises(NotificationHubError):
            hub.send_template_notification({"message": "Hello"})
        assert len(mock.calls) == 1

    assert sleeps == []


def test_forbidden_is_retried_only_with_retry_after(hub, sleeps):
    with sequence(403) as mock:
        with pytest.raises(NotificationHubError):
            hub.send_template_notification({"message": "Hello"})
        assert len(mock.calls) == 1

    with sequence(403, 201, headers={"Retry-After": "2"}) as mock:
        hub.send_template_notification({"message": "Hello"})
        assert len(mock.calls) == 2


def test_error_carries_the_service_details(hub, failing_hub_api):
    with pytest.raises(NotificationHubError) as error:
        hub.send_template_notification({"message": "Hello"})

    assert isinstance(error.value, Exception)
    assert error.value.status_code == 400
    assert error.value.code == "400"
    assert error.value.detail == "Bad request"


def test_logs_never_contain_the_sas_token(hub, hub_api, caplog):
    caplog.set_level(logging.DEBUG, logger="notificationhubs_rest_python")
    hub_with_debug = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, debug=1)

    hub.send_template_notification({"message": "Hello"})
    hub_with_debug.send_template_notification({"message": "Hello"})

    assert caplog.records
    assert "SharedAccessSignature" not in caplog.text
