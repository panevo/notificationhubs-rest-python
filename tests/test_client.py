"""Behaviour of the 2.0 client: hub name, API version, SAS tokens, success codes and logging."""

import logging

import pytest
import responses

from conftest import ANY_HUB_URL, CONNECTION_STRING, HUB_NAME, assert_valid_sas_token, split_request
from notificationhubs_rest_python import AzureNotificationHub


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


def test_200_counts_as_success(hub):
    with responses.RequestsMock() as mock:
        mock.add(responses.POST, ANY_HUB_URL, status=200)
        status, _ = hub.send_template_notification({"message": "Hello"})

    assert status == 200


def test_logs_never_contain_the_sas_token(hub, hub_api, caplog):
    caplog.set_level(logging.DEBUG, logger="notificationhubs_rest_python")
    hub_with_debug = AzureNotificationHub(CONNECTION_STRING, HUB_NAME, debug=1)

    hub.send_template_notification({"message": "Hello"})
    hub_with_debug.send_template_notification({"message": "Hello"})

    assert caplog.records
    assert "[redacted]" in caplog.text
    assert "SharedAccessSignature" not in caplog.text
