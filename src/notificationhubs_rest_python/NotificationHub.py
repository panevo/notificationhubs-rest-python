"""Client for the Azure Notification Hubs REST API.

Reference: https://learn.microsoft.com/en-us/rest/api/notificationhubs/
"""

import json
import logging
from collections import abc
from datetime import datetime
from typing import AbstractSet, Any, Dict, Optional, Tuple, Union

from notificationhubs_rest_python._connection_string import parse_connection_string
from notificationhubs_rest_python._sas import SasTokenProvider
from notificationhubs_rest_python._transport import Timeout, Transport
from notificationhubs_rest_python.errors import NotificationHubError

logger = logging.getLogger("notificationhubs_rest_python")

API_VERSION = "2020-06"
REDACTED = "[redacted]"

# Formats whose payload is sent as JSON. The others (windows, windowsphone) are sent as XML.
JSON_FORMATS = ("template", "apple", "gcm", "adm", "baidu")

# A tag, a tag expression, or a set of tags that is sent as an OR expression
Tags = Union[str, AbstractSet[str], None]

# The HTTP status and the headers that were sent, with the SAS token redacted
SendResult = Tuple[int, Dict[str, str]]


class AzureNotification:
    VALID_FORMATS = ("template", "apple", "gcm", "windows", "windowsphone", "adm", "baidu")

    def __init__(self, notification_format: Optional[str] = None, payload: Any = None):
        if notification_format not in self.VALID_FORMATS:
            raise ValueError(
                "Invalid Notification format. Must be one of the following - "
                + ", ".join(f"'{name}'" for name in self.VALID_FORMATS)
            )

        self.format = notification_format
        self.payload = payload

        # Extra headers to send with this notification, such as X-WNS-Type for Windows or
        # apns-priority for Apple.
        self.headers: Optional[Dict[str, str]] = None


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
            payload_to_send = json.dumps(notification.payload)
        else:
            content_type = "application/xml"
            payload_to_send = notification.payload

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
            # scheduled_time must be UTC
            headers[self.SCHEDULED_NOTIFICATION_HEADER_NAME] = scheduled_time.strftime("%Y-%m-%d'T'%H:%M:%S")

        if is_direct:
            if device_handle is None:
                raise ValueError("Error sending direct notification. Missing PNS device handle.")
            url += "/?direct&" + self.API_VERSION
            headers[self.DEVICE_TOKEN_HEADER_NAME] = device_handle
        else:
            url += "/?" + self.API_VERSION

        tags: Optional[str]
        if isinstance(tag_or_tag_expression, abc.Set):
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

    def __make_http_request(self, url: str, payload: Any, headers: Dict[str, str]) -> int:
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
        nh = AzureNotification("gcm", payload)
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
        nh = AzureNotification("windowsphone", payload)

        if "<wp:Toast>" in payload:
            nh.headers = {"X-WindowsPhone-Target": "toast", "X-NotificationClass": "2"}
        elif "<wp:Tile>" in payload:
            nh.headers = {"X-WindowsPhone-Target": "tile", "X-NotificationClass": "1"}

        return self.__send_notification(
            nh,
            is_direct=is_direct,
            tag_or_tag_expression=tags,
            device_handle=device_handle,
            scheduled_time=scheduled_time,
            skip_send=skip_send,
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

        if "<toast>" in payload:
            nh.headers = {"X-WNS-Type": "wns/toast"}
        elif "<tile>" in payload:
            nh.headers = {"X-WNS-Type": "wns/tile"}
        elif "<badge>" in payload:
            nh.headers = {"X-WNS-Type": "wns/badge"}

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


def _redact(headers: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of the headers with the SAS token hidden."""
    redacted = dict(headers)
    if "Authorization" in redacted:
        redacted["Authorization"] = REDACTED
    return redacted
