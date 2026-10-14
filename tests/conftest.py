import base64
import hashlib
import hmac
import json
import re
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, quote, urlsplit

import pytest
import responses

ENDPOINT = "https://example.servicebus.windows.net/"
HUB_NAME = "hub"
KEY_NAME = "DefaultFullSharedAccessSignature"
KEY = "dGVzdC1rZXk="
CONNECTION_STRING = (
    "Endpoint=sb://example.servicebus.windows.net/;SharedAccessKeyName=" + KEY_NAME + ";SharedAccessKey=" + KEY
)
ANY_HUB_URL = re.compile(r"https://[a-z]+\.servicebus\.windows\.net/.*")


@pytest.fixture
def hub():
    from notificationhubs_rest_python import AzureNotificationHub

    return AzureNotificationHub(CONNECTION_STRING, HUB_NAME)


@pytest.fixture
def sleeps(monkeypatch):
    """Record retry delays instead of sleeping."""
    delays = []
    monkeypatch.setattr(
        "notificationhubs_rest_python._transport.time", SimpleNamespace(sleep=delays.append, time=time.time)
    )
    return delays


@pytest.fixture
def hub_api():
    """Fake Notification Hubs API that accepts every request with 201 Created."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        mock.add(responses.POST, ANY_HUB_URL, status=201)
        yield mock


@pytest.fixture
def failing_hub_api():
    """Fake Notification Hubs API that rejects every request with 400 Bad Request."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        mock.add(
            responses.POST,
            ANY_HUB_URL,
            status=400,
            body="<Error><Code>400</Code><Detail>Bad request</Detail></Error>",
        )
        yield mock


def split_request(request):
    """Return the path, query parameters, headers and body of a recorded request."""
    url = urlsplit(request.url)
    body = request.body.decode() if isinstance(request.body, bytes) else request.body
    return url.path, parse_qs(url.query, keep_blank_values=True), request.headers, body


def json_body(request):
    return json.loads(split_request(request)[3])


def assert_valid_sas_token(token, key=KEY, key_name=KEY_NAME, resource=ENDPOINT + HUB_NAME):
    """Check that a SAS token is well formed, not expired and signed with the key."""
    prefix = "SharedAccessSignature "
    assert token.startswith(prefix)
    fields = dict(part.split("=", 1) for part in token[len(prefix) :].split("&"))
    assert fields["sr"] == quote(resource, safe="").lower()
    assert fields["skn"] == key_name
    expiry = int(fields["se"])
    assert expiry > time.time()
    to_sign = "{}\n{}".format(fields["sr"], expiry).encode()
    expected = base64.b64encode(hmac.new(key.encode(), to_sign, hashlib.sha256).digest()).decode()
    # The base64 signature is URL encoded, so that a "+" in it is not read as a space
    assert fields["sig"] == quote(expected)
