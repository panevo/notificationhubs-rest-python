"""Client for the Azure Notification Hubs REST API.

Reference: https://learn.microsoft.com/en-us/rest/api/notificationhubs/
"""

import json
import logging
import re
from collections import abc
from datetime import datetime, timezone
from typing import Any, Optional, Union

from notificationhubs_rest_python._connection_string import parse_connection_string
from notificationhubs_rest_python._sas import SasTokenProvider
from notificationhubs_rest_python._transport import Timeout, Transport
from notificationhubs_rest_python.errors import NotificationHubError

logger = logging.getLogger("notificationhubs_rest_python")

API_VERSION = "2020-06"
REDACTED = "[redacted]"

# Formats whose payload is sent as JSON. Windows payloads are sent as XML.
JSON_FORMATS = ("template", "apple", "fcmV1", "adm", "baidu")

# Formats that no longer work, with what to use instead
RETIRED_FORMATS = {
    "gcm": "Google shut down the legacy GCM/FCM API on 2024-06-20. Use 'fcmV1' instead.",
    "windowsphone": "Microsoft no longer supports MPNS (Windows Phone).",
}

# The root element of a Windows (WNS) payload decides its X-WNS-Type header
WNS_ROOT_ELEMENT = re.compile(r"\s*(?:<\?xml[^>]*\?>\s*)?<(toast|tile|badge)[\s/>]")

# A tag, a tag expression, or a set of tags that is sent as an OR expression
Tags = Union[str, abc.Set[str], None]

# The HTTP status and the headers that were sent, with the SAS token redacted
SendResult = tuple[int, dict[str, str]]


class AzureNotification:
    VALID_FORMATS = ("template", "apple", "fcmV1", "windows", "adm", "baidu")

    def __init__(self, notification_format: Optional[str] = None, payload: Any = None):
        if notification_format in RETIRED_FORMATS:
            raise ValueError(
                f"The '{notification_format}' format is no longer supported. {RETIRED_FORMATS[notification_format]}"
            )
        if notification_format not in self.VALID_FORMATS:
            raise ValueError(
                "Invalid Notification format. Must be one of the following - "
                + ", ".join(f"'{name}'" for name in self.VALID_FORMATS)
            )

        self.format = notification_format
        self.payload = payload

        # Extra headers to send with this notification, such as X-WNS-Type for Windows or
        # apns-priority for Apple.
        self.headers: Optional[dict[str, str]] = None


class AzureNotificationHub:
    DEVICE_TOKEN_HEADER_NAME = "ServiceBusNotification-DeviceHandle"
    TAGS_HEADER_NAME = "ServiceBusNotification-Tags"
    API_VERSION = "api-version=" + API_VERSION
    DEBUG_SEND = "&test"
    SCHEDULED_NOTIFICATION_HEADER_NAME = "ServiceBusNotification-ScheduleTime"
    SCHEDULED_NOTIFICATION_FORMAT_HEADER_NAME = "ServiceBusNotification-Format"

    def __init__(
        self,
        connection_string: Optional[str] = None,
        hub_name: Optional[str] = None,
        debug: int = 0,
        *,
        timeout: Timeout = (10, 30),
        max_retries: int = 3,
    ) -> None:
        """Create a client for one notification hub.

        Args:
            connection_string: The hub's connection string from the Azure portal.
            hub_name: The name of the notification hub.
            debug: Send test notifications (the ``test`` query parameter) and log the outcome.
            timeout: Seconds to wait for the connection and for the response, as for ``requests``.
            max_retries: How often to retry a send that was throttled or failed with a transient
                error. 0 switches retries off.
        """
        endpoint, key_name, key = parse_connection_string(connection_string)
        if hub_name is None:
            raise ValueError("Missing hub name: pass the name of the notification hub")
        self.HubName = hub_name
        self.Debug = debug
        self.Endpoint = endpoint
        self.SasKeyName = key_name
        self.SasKeyValue = key
        self._sas_tokens = SasTokenProvider(endpoint + hub_name, key_name, key)
        self._transport = Transport(timeout=timeout, max_retries=max_retries)

    def generate_sas_token(self) -> str:
        """Return a SAS token for the hub, to send in the ``Authorization`` header."""
        return self._sas_tokens.token()

    def __generate_sas_token(self) -> str:
        # The 1.x name, which code that extends this class calls as
        # self._AzureNotificationHub__generate_sas_token(). Kept working on purpose.
        return self.generate_sas_token()

    def __send_notification(
        self,
        notification: AzureNotification,
        is_direct: bool,
        tag_or_tag_expression: Tags = None,
        scheduled_time: Optional[datetime] = None,
        device_handle: Optional[str] = None,
        skip_send: bool = False,
    ) -> SendResult:
        if notification.format in JSON_FORMATS:
            content_type = "application/json"
            body = json.dumps(notification.payload)
        else:
            content_type = "application/xml"
            body = notification.payload
        # Send UTF-8: requests with urllib3 1.x would send a str body as Latin-1
        payload_to_send = body.encode("utf-8")

        headers = {
            "Content-type": content_type,
            "Authorization": self.generate_sas_token(),
            self.SCHEDULED_NOTIFICATION_FORMAT_HEADER_NAME: notification.format,
            "x-ms-version": API_VERSION,
        }

        url = self.Endpoint + self.HubName

        if scheduled_time is None:
            url += "/messages"
        else:
            url += "/schedulednotifications"
            headers[self.SCHEDULED_NOTIFICATION_HEADER_NAME] = _format_schedule_time(scheduled_time)

        if is_direct:
            if device_handle is None:
                raise ValueError("Error sending direct notification. Missing PNS device handle.")
            url += "/?direct&" + self.API_VERSION
            headers[self.DEVICE_TOKEN_HEADER_NAME] = device_handle
        else:
            url += "/?" + self.API_VERSION

        tags: Optional[str]
        if isinstance(tag_or_tag_expression, abc.Set):
            if not tag_or_tag_expression:
                # An empty tags header sends the notification to every device
                raise ValueError("The set of tags must contain at least one tag. Use tags='' to send to all devices.")
            tags = " || ".join(sorted(tag_or_tag_expression))
        else:
            tags = tag_or_tag_expression
        if tags:
            headers[self.TAGS_HEADER_NAME] = tags

        if notification.headers is not None:
            headers.update(notification.headers)

        if skip_send:
            return 201, _redact(headers)

        if self.Debug > 0:
            # Sends a test notification and returns the outcome per device
            url += self.DEBUG_SEND

        status = self.__make_http_request(url, payload_to_send, headers)
        return status, _redact(headers)

    def __make_http_request(self, url: str, payload: bytes, headers: dict[str, str]) -> int:
        logger.debug("Sending notification: POST %s, headers %s", url, _redact(headers))
        response = self._transport.post(url, payload, headers)
        logger.debug(
            "Notification Hubs response: %s %s, headers %s",
            response.status_code,
            response.reason,
            dict(response.headers),
        )
        if self.Debug > 0:
            logger.info("Test send outcome: %s %s\n%s", response.status_code, response.reason, response.text)

        if response.status_code not in (200, 201):
            raise NotificationHubError.from_response(response)
        return response.status_code

    def send_apple_notification(
        self,
        is_direct: bool,
        payload: Any,
        tags: Tags = "",
        device_handle: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        skip_send: bool = False,
    ) -> SendResult:
        nh = AzureNotification("apple", payload)
        return self.__send_notification(
            nh,
            is_direct=is_direct,
            tag_or_tag_expression=tags,
            device_handle=device_handle,
            scheduled_time=scheduled_time,
            skip_send=skip_send,
        )

    def send_google_notification(
        self,
        is_direct: bool,
        payload: Any,
        tags: Tags = "",
        device_handle: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        skip_send: bool = False,
    ) -> SendResult:
        """Send an Android notification through Firebase Cloud Messaging (FCM) v1.

        The payload uses the FCM v1 format, wrapped in a "message" object, for example
        {"message": {"notification": {"title": "Hi", "body": "Hello"}}}. Leave out the device
        token: Notification Hubs adds it.
        """
        if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
            raise ValueError(
                "send_google_notification sends FCM v1 notifications, which need the payload wrapped in a "
                "'message' object, for example {'message': {'notification': {'title': 'Hi', 'body': 'Hello'}}}. "
                "The legacy GCM/FCM format is no longer supported by Google."
            )
        nh = AzureNotification("fcmV1", payload)
        return self.__send_notification(
            nh,
            is_direct=is_direct,
            tag_or_tag_expression=tags,
            device_handle=device_handle,
            scheduled_time=scheduled_time,
            skip_send=skip_send,
        )

    def send_amazon_notification(
        self,
        is_direct: bool,
        payload: Any,
        tags: Tags = "",
        device_handle: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        skip_send: bool = False,
    ) -> SendResult:
        nh = AzureNotification("adm", payload)
        return self.__send_notification(
            nh,
            is_direct=is_direct,
            tag_or_tag_expression=tags,
            device_handle=device_handle,
            scheduled_time=scheduled_time,
            skip_send=skip_send,
        )

    def send_baidu_notification(
        self,
        is_direct: bool,
        payload: Any,
        tags: Tags = "",
        device_handle: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        skip_send: bool = False,
    ) -> SendResult:
        nh = AzureNotification("baidu", payload)
        return self.__send_notification(
            nh,
            is_direct=is_direct,
            tag_or_tag_expression=tags,
            device_handle=device_handle,
            scheduled_time=scheduled_time,
            skip_send=skip_send,
        )

    def send_windows_phone_notification(
        self,
        is_direct: bool,
        payload: str,
        tags: Tags = "",
        device_handle: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        skip_send: bool = False,
    ) -> SendResult:
        """No longer supported: Microsoft retired MPNS, the Windows Phone push service."""
        raise NotImplementedError(
            "Windows Phone notifications are no longer supported, because Microsoft no longer supports MPNS. "
            "Use send_windows_notification for Windows (WNS) devices."
        )

    # example wns payload =
    # <toast><visual><binding template="ToastText01"><text id="1">Python Test</text></binding></visual></toast>
    def send_windows_notification(
        self,
        is_direct: bool,
        payload: str,
        tags: Tags = "",
        device_handle: Optional[str] = None,
        scheduled_time: Optional[datetime] = None,
        skip_send: bool = False,
    ) -> SendResult:
        nh = AzureNotification("windows", payload)

        root_element = WNS_ROOT_ELEMENT.match(payload)
        if root_element:
            nh.headers = {"X-WNS-Type": "wns/" + root_element.group(1)}

        return self.__send_notification(
            nh,
            is_direct=is_direct,
            tag_or_tag_expression=tags,
            device_handle=device_handle,
            scheduled_time=scheduled_time,
            skip_send=skip_send,
        )

    def send_template_notification(
        self,
        properties: Any,
        tags: Tags = "",
        scheduled_time: Optional[datetime] = None,
        skip_send: bool = False,
    ) -> SendResult:
        nh = AzureNotification("template", properties)
        return self.__send_notification(
            nh, is_direct=False, tag_or_tag_expression=tags, scheduled_time=scheduled_time, skip_send=skip_send
        )


def _format_schedule_time(scheduled_time: datetime) -> str:
    """Format the time for the ScheduleTime header in UTC. A time without a timezone is taken as UTC."""
    if scheduled_time.tzinfo is not None:
        scheduled_time = scheduled_time.astimezone(timezone.utc)
    return scheduled_time.strftime("%Y-%m-%dT%H:%M:%S")


def _redact(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of the headers with the SAS token hidden."""
    redacted = dict(headers)
    if "Authorization" in redacted:
        redacted["Authorization"] = REDACTED
    return redacted
