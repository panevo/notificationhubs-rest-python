"""Retrying throttled and failed sends, and request timeouts."""

import logging
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
import requests
import responses
from responses.registries import OrderedRegistry

from conftest import ANY_HUB_URL, CONNECTION_STRING, HUB_NAME
from notificationhubs_rest_python import AzureNotificationHub, NotificationHubError


def sequence(*responses_to_send):
    """A fake API that answers each request with the next (status, headers) in the list."""
    mock = responses.RequestsMock(registry=OrderedRegistry)
    for status, headers in responses_to_send:
        mock.add(responses.POST, ANY_HUB_URL, status=status, headers=headers)
    return mock


def send(hub):
    return hub.send_template_notification({"message": "Hello"})


@pytest.mark.parametrize("status", [408, 429, 500, 503, 504])
def test_transient_errors_are_retried(hub, sleeps, status):
    with sequence((status, None), (201, None)) as mock:
        result, _ = send(hub)
        assert len(mock.calls) == 2

    assert result == 201
    assert len(sleeps) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 410, 413, 502])
def test_other_errors_are_not_retried(hub, sleeps, status):
    with sequence((status, None)) as mock:
        with pytest.raises(NotificationHubError) as error:
            send(hub)
        assert len(mock.calls) == 1

    assert error.value.status_code == status
    assert sleeps == []


@pytest.mark.parametrize(
    ("retry_after", "delay"),
    [("7", 7), ("0", 0), ("1.5", 1.5), ("-5", 0), ("120", 60)],
)
def test_retry_after_in_seconds(hub, sleeps, retry_after, delay):
    with sequence((429, {"Retry-After": retry_after}), (201, None)):
        send(hub)

    assert sleeps == [delay]


def test_retry_after_as_a_date(hub, sleeps):
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=30)

    with sequence((503, {"Retry-After": format_datetime(retry_at, usegmt=True)}), (201, None)):
        send(hub)

    [delay] = sleeps
    assert 28 <= delay <= 30


def test_retry_after_date_in_the_past(hub, sleeps):
    with sequence((503, {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}), (201, None)):
        send(hub)

    assert sleeps == [0]


@pytest.mark.parametrize("retry_after", ["soon", "", "nan", "inf", "-inf"])
def test_invalid_retry_after_falls_back_to_backoff(hub, sleeps, retry_after):
    with sequence((429, {"Retry-After": retry_after}), (201, None)):
        send(hub)

    [delay] = sleeps
    assert 1.0 <= delay <= 1.2


def test_backoff_doubles_with_jitter(hub, sleeps):
    with sequence((503, None), (503, None), (503, None), (201, None)):
        send(hub)

    first, second, third = sleeps
    assert 1.0 <= first <= 1.2
    assert 2.0 <= second <= 2.4
    assert 4.0 <= third <= 4.8


def test_backoff_is_capped_at_a_minute(sleeps):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, max_retries=8)

    with sequence(*[(503, None)] * 8, (201, None)):
        send(hub)

    assert len(sleeps) == 8
    assert sleeps[-2:] == [60, 60]


def test_retries_are_logged_as_warnings(hub, sleeps, caplog):
    caplog.set_level(logging.WARNING, logger="notificationhubs_rest_python")

    with sequence((503, {"Retry-After": "2"}), (201, None)):
        send(hub)

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "503" in record.getMessage()
    assert "retrying in 2.0 s" in record.getMessage()


@pytest.mark.parametrize("network_error", [requests.ConnectionError("refused"), requests.ReadTimeout("timed out")])
def test_network_errors_are_not_retried(hub, sleeps, network_error):
    # A notification that timed out may still have been sent, so retrying could send it twice
    with responses.RequestsMock() as mock:
        mock.add(responses.POST, ANY_HUB_URL, body=network_error)
        with pytest.raises(type(network_error)):
            send(hub)
        assert len(mock.calls) == 1

    assert sleeps == []


def test_default_timeout(hub, hub_api):
    send(hub)

    [call] = hub_api.calls
    assert call.request.req_kwargs["timeout"] == (10, 30)


@pytest.mark.parametrize("timeout", [5, 2.5, (3, 7)])
def test_custom_timeout(hub_api, timeout):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, timeout=timeout)

    send(hub)

    [call] = hub_api.calls
    assert call.request.req_kwargs["timeout"] == timeout


def test_retries_stop_after_three_attempts(hub, sleeps):
    with sequence(*[(503, None)] * 4) as mock:
        with pytest.raises(NotificationHubError) as error:
            send(hub)
        assert len(mock.calls) == 4

    assert len(sleeps) == 3
    assert error.value.status_code == 503


def test_retries_can_be_switched_off(sleeps):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, max_retries=0)

    with sequence((503, None)) as mock:
        with pytest.raises(NotificationHubError):
            send(hub)
        assert len(mock.calls) == 1

    assert sleeps == []


def test_forbidden_is_retried_when_the_service_sends_retry_after(hub, sleeps):
    # Notification Hubs answers 403 with Retry-After when a quota is temporarily exceeded
    with sequence((403, {"Retry-After": "2"}), (201, None)) as mock:
        status, _ = send(hub)
        assert len(mock.calls) == 2

    assert status == 201
    assert sleeps == [2]
