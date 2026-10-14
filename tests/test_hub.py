"""Creating a hub, and extending it with requests of your own."""

from concurrent.futures import ThreadPoolExecutor

from conftest import CONNECTION_STRING, ENDPOINT, HUB_NAME, assert_valid_sas_token, split_request
from notificationhubs_rest_python.NotificationHub import AzureNotificationHub


class HubWithInstallations(AzureNotificationHub):
    """A subclass that builds its own installation requests from the hub's attributes and SAS token."""

    def installation_request(self, installation_id):
        url = f"{self.Endpoint}{self.HubName}/installations/{installation_id}"
        headers = {
            "Content-Type": "application/json",
            "Authorization": self._AzureNotificationHub__generate_sas_token(),
            "x-ms-version": "2015-01",
        }
        return url, headers


def test_subclass_can_build_its_own_requests():
    hub = HubWithInstallations(CONNECTION_STRING, HUB_NAME, False)

    url, headers = hub.installation_request("device-1")

    assert hub.Endpoint == ENDPOINT
    assert hub.HubName == HUB_NAME
    assert url == "https://example.servicebus.windows.net/hub/installations/device-1"
    assert_valid_sas_token(headers["Authorization"])


def test_sas_tokens_are_valid_across_threads():
    hub = HubWithInstallations(CONNECTION_STRING, HUB_NAME, False)

    with ThreadPoolExecutor(max_workers=8) as executor:
        tokens = list(executor.map(lambda _: hub.installation_request("device-1")[1]["Authorization"], range(50)))

    for token in tokens:
        assert_valid_sas_token(token)


def test_sas_token_follows_changes_to_the_hub_attributes(hub_api):
    hub = AzureNotificationHub(CONNECTION_STRING, HUB_NAME)
    hub.generate_sas_token()
    hub.Endpoint = "https://other.servicebus.windows.net/"
    hub.HubName = "other-hub"
    hub.SasKeyName = "OtherKeyName"
    hub.SasKeyValue = "b3RoZXIta2V5"

    hub.send_template_notification({"message": "Hello"})

    [call] = hub_api.calls
    assert call.request.url.startswith("https://other.servicebus.windows.net/other-hub/")
    assert_valid_sas_token(
        split_request(call.request)[2]["Authorization"],
        key="b3RoZXIta2V5",
        key_name="OtherKeyName",
        resource="https://other.servicebus.windows.net/other-hub",
    )


def test_connection_string_with_empty_values_is_accepted():
    # For example a placeholder used when notifications are switched off
    AzureNotificationHub("Endpoint=/;SharedAccessKeyName=;SharedAccessKey=", "", False)
