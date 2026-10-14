import base64
import hashlib
import hmac
import threading
import time
from typing import Optional, Tuple
from urllib.parse import quote


class SasTokenProvider:
    """Creates SAS tokens and reuses each token until it is close to expiring.

    A new token is created when the resource or the key changes. Safe to use from several threads.
    """

    def __init__(self, lifetime: int = 3600, renew_before: int = 300):
        self._lifetime = lifetime
        self._renew_before = renew_before
        self._lock = threading.Lock()
        self._credentials: Optional[Tuple[str, str, str]] = None
        self._token = ""
        self._expiry = 0

    def token(self, resource_uri: str, key_name: str, key: str) -> str:
        credentials = (resource_uri, key_name, key)
        with self._lock:
            if credentials != self._credentials or time.time() > self._expiry - self._renew_before:
                self._credentials = credentials
                self._expiry = int(time.time()) + self._lifetime
                self._token = _create(resource_uri, key_name, key, self._expiry)
            return self._token


def _create(resource_uri: str, key_name: str, key: str, expiry: int) -> str:
    resource = quote(resource_uri, safe="").lower()
    to_sign = f"{resource}\n{expiry}".encode()
    digest = hmac.new(key.encode("utf-8"), to_sign, hashlib.sha256).digest()
    signature = quote(base64.b64encode(digest))
    return f"SharedAccessSignature sig={signature}&se={expiry}&skn={key_name}&sr={resource}"
