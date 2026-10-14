import requests

from notificationhubs_rest_python.NotificationHub import AzureNotificationHub

CONNECTION_STRING = (
    "Endpoint=sb://example.servicebus.windows.net/;"
    "SharedAccessKeyName=DefaultFullSharedAccessSignature;"
    "SharedAccessKey=dGVzdA=="
)


class FakeResponse:
    status_code = 201
    reason = "Created"

    def close(self):
        pass


def test_send_template_notification(monkeypatch):
    requests_sent = []

    def fake_post(url, data=None, headers=None):
        requests_sent.append((url, data, headers))
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    hub = AzureNotificationHub(CONNECTION_STRING, "hub")
    status, _ = hub.send_template_notification({"message": "Hello"}, tags="news")

    assert status == 201
    [(url, data, headers)] = requests_sent
    assert url == "https://example.servicebus.windows.net/hub/messages/?api-version=2015-04"
    assert data == '{"message": "Hello"}'
    assert headers["ServiceBusNotification-Format"] == "template"
    assert headers["ServiceBusNotification-Tags"] == "news"
    assert headers["Authorization"].startswith("SharedAccessSignature sig=")
