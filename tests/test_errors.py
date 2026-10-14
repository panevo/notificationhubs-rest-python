"""Errors from Notification Hubs."""

import pytest
import responses

from conftest import ANY_HUB_URL
from notificationhubs_rest_python import NotificationHubError
from notificationhubs_rest_python.errors import NotificationHubError as ErrorFromModule


def fail_with(hub, status, body):
    with responses.RequestsMock() as mock:
        mock.add(responses.POST, ANY_HUB_URL, status=status, body=body)
        with pytest.raises(NotificationHubError) as error:
            hub.send_template_notification({"message": "Hello"})
    return error.value


def test_error_with_the_service_details(hub):
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        "<Error><Code>400</Code><Detail>The payload is invalid.TrackingId:1234</Detail></Error>"
    )

    error = fail_with(hub, 400, body)

    assert (error.status_code, error.reason, error.code) == (400, "Bad Request", "400")
    assert error.detail == "The payload is invalid.TrackingId:1234"
    assert str(error) == (
        "Error sending notification. Received HTTP code 400 Bad Request: The payload is invalid.TrackingId:1234"
    )


@pytest.mark.parametrize(
    "body",
    ["", "Service Unavailable", "<html><body>Bad gateway</body>", "<Error><Unexpected/></Error>"],
)
def test_error_without_service_details(hub, body):
    error = fail_with(hub, 401, body)

    assert (error.status_code, error.code, error.detail) == (401, None, None)
    assert str(error) == "Error sending notification. Received HTTP code 401 Unauthorized"


def test_error_is_an_exception_for_code_written_for_1x(hub):
    error = fail_with(hub, 404, "")

    assert isinstance(error, Exception)
    assert NotificationHubError is ErrorFromModule
