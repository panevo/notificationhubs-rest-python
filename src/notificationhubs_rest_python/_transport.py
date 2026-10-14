import logging
import random
import time
from collections.abc import Mapping
from email.utils import parsedate_to_datetime
from typing import Optional, Union

import requests

logger = logging.getLogger("notificationhubs_rest_python")

# Status codes worth retrying, as in Microsoft's .NET and Java SDKs. 403 is only retried when the
# service sends Retry-After, which it does when a quota is temporarily exceeded.
RETRY_STATUS_CODES = {408, 429, 500, 503, 504}

Timeout = Union[float, tuple[float, float]]


class Transport:
    """Sends requests over one reused HTTP session, with timeouts and retries."""

    def __init__(self, timeout: Timeout, max_retries: int, base_delay: float = 1.0, max_delay: float = 60.0):
        self.session = requests.Session()
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def post(self, url: str, data: Union[str, bytes], headers: Mapping[str, str]) -> requests.Response:
        attempt = 0
        while True:
            response = self.session.post(url, data=data, headers=headers, timeout=self.timeout)
            if attempt >= self.max_retries or not self._should_retry(response):
                return response
            delay = self._delay(response, attempt)
            logger.warning(
                "Notification Hubs returned %s %s, retrying in %.1f s", response.status_code, response.reason, delay
            )
            response.close()
            time.sleep(delay)
            attempt += 1

    @staticmethod
    def _should_retry(response: requests.Response) -> bool:
        if response.status_code in RETRY_STATUS_CODES:
            return True
        return response.status_code == 403 and "Retry-After" in response.headers

    def _delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = self._retry_after(response)
        if retry_after is not None:
            return min(retry_after, self.max_delay)
        backoff = self.base_delay * 2.0**attempt
        return min(backoff * random.uniform(1.0, 1.2), self.max_delay)

    @staticmethod
    def _retry_after(response: requests.Response) -> Optional[float]:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return max(float(value), 0.0)
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        return max(retry_at.timestamp() - time.time(), 0.0)
