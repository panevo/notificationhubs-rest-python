import base64
import hashlib
import hmac
import threading
import time
from typing import Optional
from urllib.parse import quote


class SasTokenProvider:
    """Creates SAS tokens for a hub and reuses each token until it is close to expiring.

    Safe to use from several threads.
    """

    def __init__(self, resource_uri: str, key_name: str, key: str, lifetime: int = 3600, renew_before: int = 300):
        self._resource = quote(resource_uri, safe="").lower()
        self._key_name = key_name
        self._key = key
        self._lifetime = lifetime
        self._renew_before = renew_before
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._expiry = 0

    def token(self) -> str:
        with self._lock:
            if self._token is None or time.time() > self._expiry - self._renew_before:
                self._expiry = int(time.time()) + self._lifetime
                self._token = self._create(self._expiry)
            return self._token

    def _create(self, expiry: int) -> str:
        to_sign = f"{self._resource}\n{expiry}".encode()
        digest = hmac.new(self._key.encode("utf-8"), to_sign, hashlib.sha256).digest()
        signature = quote(base64.b64encode(digest))
        return f"SharedAccessSignature sig={signature}&se={expiry}&skn={self._key_name}&sr={self._resource}"
