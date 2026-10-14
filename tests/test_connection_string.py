"""Reading the connection string from the Azure portal."""

import pytest

from conftest import CONNECTION_STRING, ENDPOINT, HUB_NAME, KEY, KEY_NAME
from notificationhubs_rest_python import AzureNotificationHub


def credentials(hub):
    return hub.Endpoint, hub.SasKeyName, hub.SasKeyValue


def test_connection_string_from_the_portal():
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)

    assert credentials(hub) == (ENDPOINT, KEY_NAME, KEY)


@pytest.mark.parametrize(
    "connection_string",
    [CONNECTION_STRING + ";\n", "  " + CONNECTION_STRING + "\n", CONNECTION_STRING.replace(";", " ;\n ")],
)
def test_surrounding_whitespace_is_ignored(connection_string):
    hub = AzureNotificationHub(connection_string, HUB_NAME)

    assert credentials(hub) == (ENDPOINT, KEY_NAME, KEY)


def test_names_are_case_insensitive():
    connection_string = (
        "endpoint=sb://example.servicebus.windows.net/;sharedaccesskeyname=" + KEY_NAME + ";SHAREDACCESSKEY=" + KEY
    )

    hub = AzureNotificationHub(connection_string, HUB_NAME)

    assert credentials(hub) == (ENDPOINT, KEY_NAME, KEY)


def test_key_keeps_its_base64_padding():
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)

    assert KEY.endswith("=")
    assert hub.SasKeyValue == KEY


@pytest.mark.parametrize(
    "endpoint",
    [
        "sb://example.servicebus.windows.net/",
        "sb://example.servicebus.windows.net",
        "https://example.servicebus.windows.net/",
        "https://example.servicebus.windows.net",
    ],
)
def test_endpoint_is_https_with_a_trailing_slash(endpoint):
    connection_string = f"Endpoint={endpoint};SharedAccessKeyName={KEY_NAME};SharedAccessKey={KEY}"

    hub = AzureNotificationHub(connection_string, HUB_NAME)

    assert hub.Endpoint == ENDPOINT


def test_other_parts_are_ignored():
    hub = AzureNotificationHub(CONNECTION_STRING + ";EntityPath=" + HUB_NAME, HUB_NAME)

    assert credentials(hub) == (ENDPOINT, KEY_NAME, KEY)


@pytest.mark.parametrize(
    ("connection_string", "message"),
    [
        (None, "expected a string"),
        (CONNECTION_STRING.encode(), "expected a string"),
        ("", "missing Endpoint, SharedAccessKeyName, SharedAccessKey$"),
        ("empty", "expected name=value parts"),
        ("Endpoint=sb://example.servicebus.windows.net/;SharedAccessKeyName=" + KEY_NAME, "missing SharedAccessKey$"),
        ("SharedAccessKeyName=" + KEY_NAME + ";SharedAccessKey=" + KEY, "missing Endpoint$"),
    ],
)
def test_invalid_connection_string_raises(connection_string, message):
    with pytest.raises(ValueError, match="Invalid connection string: " + message):
        AzureNotificationHub(connection_string, HUB_NAME)
