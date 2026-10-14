"""Errors raised by the Notification Hubs client."""

from typing import Optional
from xml.etree import ElementTree

import requests


class NotificationHubError(Exception):
    """Notification Hubs rejected a request.

    It subclasses ``Exception``, so code written for 1.x that catches ``Exception`` keeps working.
    """

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        reason: Optional[str] = None,
        code: Optional[str] = None,
        detail: Optional[str] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.reason = reason
        self.code = code
        self.detail = detail

    @classmethod
    def from_response(cls, response: requests.Response) -> "NotificationHubError":
        """Build the error from a failed response, including the service's error code and detail."""
        code = detail = None
        # An XML declaration after leading whitespace is not valid XML
        text = response.text.strip()
        try:
            root = ElementTree.fromstring(text)
        except ElementTree.ParseError:
            # Some errors, such as a wrong key, come as plain text instead of XML
            if text and not text.startswith("<"):
                detail = text
        else:
            code = root.findtext("Code")
            detail = root.findtext("Detail")
        message = f"Error sending notification. Received HTTP code {response.status_code} {response.reason}"
        if detail:
            message += ": " + detail
        return cls(message, status_code=response.status_code, reason=response.reason, code=code, detail=detail)
