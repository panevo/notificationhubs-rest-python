"""Sends over a real HTTP connection to a local server, to check what goes over the wire."""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from conftest import HUB_NAME, KEY, KEY_NAME, assert_valid_sas_token
from notificationhubs_rest_python import AzureNotificationHub, NotificationHubError


class FakeNotificationHubs(BaseHTTPRequestHandler):
    """Records each request and answers with the next status from the server's list, or 201."""

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.server.received.append((self.path, self.headers, body))
        status, response_body = self.server.answers.pop(0) if self.server.answers else (201, b"")
        self.send_response(status)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, *args):
        pass


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    """Connect to the local server directly, also when a proxy is set in the environment."""
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(name, "127.0.0.1")


@pytest.fixture
def server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeNotificationHubs)
    server.received = []
    server.answers = []
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def endpoint(server):
    return f"http://127.0.0.1:{server.server_port}/"


@pytest.fixture
def hub(endpoint):
    return AzureNotificationHub(
        f"Endpoint={endpoint};SharedAccessKeyName={KEY_NAME};SharedAccessKey={KEY}", HUB_NAME, max_retries=0
    )


def test_template_send(hub, server, endpoint):
    status, _ = hub.send_template_notification({"site_name": "Café ☕"}, tags="alerts && site:1")

    assert status == 201
    [(path, headers, body)] = server.received
    url = urlsplit(path)
    assert url.path == "/hub/messages/"
    assert parse_qs(url.query) == {"api-version": ["2020-06"]}
    assert headers["Content-Type"] == "application/json"
    assert headers["ServiceBusNotification-Format"] == "template"
    assert headers["ServiceBusNotification-Tags"] == "alerts && site:1"
    assert headers["x-ms-version"] == "2020-06"
    assert_valid_sas_token(headers["Authorization"], resource=endpoint + HUB_NAME)
    assert body == b'{"site_name": "Caf\\u00e9 \\u2615"}'


def test_windows_payload_is_sent_as_utf8(hub, server):
    payload = (
        '<toast><visual><binding template="ToastText01"><text id="1">Café ☕ 東京</text></binding></visual></toast>'
    )

    hub.send_windows_notification(False, payload)

    [(_, headers, body)] = server.received
    assert headers["X-WNS-Type"] == "wns/toast"
    assert body == payload.encode("utf-8")


def test_error_from_the_service(hub, server):
    server.answers.append((400, b"<Error><Code>400</Code><Detail>The payload is invalid.</Detail></Error>"))

    with pytest.raises(NotificationHubError) as error:
        hub.send_template_notification({"message": "Hello"})

    assert (error.value.status_code, error.value.code, error.value.detail) == (400, "400", "The payload is invalid.")


def test_plain_text_error_from_the_service(hub, server):
    server.answers.append((401, b"Access denied. Invalid SAS token."))

    with pytest.raises(NotificationHubError) as error:
        hub.send_template_notification({"message": "Hello"})

    assert (error.value.status_code, error.value.detail) == (401, "Access denied. Invalid SAS token.")
