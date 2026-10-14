# Notification Hubs REST wrapper for Python

![PyPI](https://img.shields.io/pypi/v/notificationhubs-rest-python?style=flat-square&cacheSeconds=3600)

A Python client for sending push notifications with [Azure Notification Hubs](https://learn.microsoft.com/en-us/azure/notification-hubs/), using its [REST API](https://learn.microsoft.com/en-us/rest/api/notificationhubs/).

The package started as Microsoft's Python sample in the [Azure Notification Hubs samples repository](https://github.com/Azure/azure-notificationhubs-samples), which Microsoft has since archived. Microsoft does not publish an official Python SDK for sending notifications, so Panevo Services Ltd. maintains this package.

## Installation

```
pip install notificationhubs-rest-python
```

This package requires Python 3.9+ and version 2.25.0+ of the `requests` package.

## Usage

Create a client with the hub's connection string and name. Use the connection string of an access policy that can send, such as `DefaultFullSharedAccessSignature`, from the hub's Access Policies in the Azure portal.

```python
from notificationhubs_rest_python import AzureNotificationHub

hub = AzureNotificationHub(connection_string, "my-hub")

# Template notification: the hub fills in each device's registered template with these properties
status, headers = hub.send_template_notification({"message": "Hello"}, tags="news && lang:en")
```

Native notifications for each platform:

```python
# Android, through Firebase Cloud Messaging (FCM) v1
hub.send_google_notification(False, {"message": {"notification": {"title": "Hi", "body": "Hello"}}}, tags="news")

# Apple (APNs)
hub.send_apple_notification(False, {"aps": {"alert": "Hello"}}, tags="news")

# Windows (WNS). The X-WNS-Type header is set from the payload's root element: toast, tile or badge
hub.send_windows_notification(
    False,
    '<toast><visual><binding template="ToastText01"><text id="1">Hello</text></binding></visual></toast>',
    tags="news",
)

# Amazon (ADM). send_baidu_notification takes the same arguments
hub.send_amazon_notification(False, {"data": {"message": "Hello"}}, tags="news")
```

### Send options

- `tags`: a tag, a tag expression such as `"news && lang:en"`, or a set of tags, which is sent as an OR expression. Without tags, the notification is sent to all devices.
- `is_direct=True` with `device_handle="..."`: send to one device instead of to tags. Not available for template notifications.
- `scheduled_time`: a `datetime` when the notification should be sent. A time without a timezone is taken as UTC. Scheduled sends need the Standard tier.
- `skip_send=True`: build the request without sending it.
- `debug=1` when creating the hub: send test notifications and log the outcome for each device. Notification Hubs sends test notifications to at most 10 devices.

Every send returns `(status, headers)`: the HTTP status, 201 or 200 on success, and the headers that were sent, with the `Authorization` value redacted.

### Errors, retries and timeouts

An error response raises `NotificationHubError`, a subclass of `Exception`, with the status code and the service's error code and detail:

```python
from notificationhubs_rest_python import NotificationHubError

try:
    hub.send_template_notification({"message": "Hello"}, tags="news")
except NotificationHubError as error:
    print(error.status_code, error.code, error.detail)
```

Throttled requests (429) and transient errors (408, 500, 503, 504, and 403 with `Retry-After`) are retried up to 3 times with exponential backoff. A `Retry-After` header from the service is honoured, up to 60 seconds. A retry can send a notification twice if the service accepted it but still returned a 500 or 504.

Each attempt times out after 10 seconds when connecting and 30 seconds when waiting for the response. Timeouts and connection errors are not retried, and raise the `requests` exceptions, such as `requests.Timeout` and `requests.ConnectionError`.

The timeouts and the number of retries can be changed. `max_retries=0` turns retries off:

```python
hub = AzureNotificationHub(connection_string, "my-hub", timeout=(5, 15), max_retries=0)
```

### Logging

The package logs to the `notificationhubs_rest_python` logger: requests and responses at `DEBUG` level, the outcome of test sends at `INFO` and retries at `WARNING`. The SAS token is never logged. Python only shows warnings and errors until logging is configured, for example with `logging.basicConfig(level=logging.INFO)`.

### SAS tokens

`hub.generate_sas_token()` returns a token for the `Authorization` header, for example to call parts of the REST API that this package does not cover. Tokens are valid for 60 minutes, and each hub object reuses its token until 5 minutes before it expires.

## Registration management

The package does not manage registrations or installations. To manage them, call the [installations API](https://learn.microsoft.com/en-us/rest/api/notificationhubs/create-overwrite-installation) with a token from `hub.generate_sas_token()`. Android devices must be registered as FCM v1 devices, see [Microsoft's FCM v1 migration guide](https://learn.microsoft.com/en-us/azure/notification-hubs/firebase-migration-rest).

## Upgrading from 1.x

- `send_google_notification` sends FCM v1 notifications, because Google shut down the legacy GCM/FCM API. Wrap the payload in a `message` object, otherwise it raises a `ValueError`, and register Android devices as FCM v1 devices.
- `send_windows_phone_notification` raises `NotImplementedError`, because Microsoft no longer supports MPNS.
- Error responses raise `NotificationHubError`, also with `debug` on, where 1.x printed the response and returned its status. It subclasses `Exception`, so existing `except Exception` blocks keep working.
- Debug output goes to the `notificationhubs_rest_python` logger instead of being printed.
- Requests time out, and throttled requests and transient errors are retried, as described above.
- Creating a hub without a hub name raises a `ValueError`.
- The headers returned by the send methods no longer contain the SAS token.
- Python 3.8 is no longer supported.

See the [changelog](https://github.com/panevo/notificationhubs-rest-python/blob/main/CHANGELOGS.md) for all changes.

## Development

Install the package with its test dependencies (`--group` needs pip 25.1 or newer) and run the tests. Any warning fails the tests.

```
pip install -e . --group test
pytest
```

To measure the coverage of the tests:

```
coverage run -m pytest
coverage combine
coverage report
```

To lint and type check the code:

```
pip install --group lint
ruff check .
ruff format --check .
mypy
```

## Notes

This code is provided as-is with no guarantees.

## Contributors

Adrian Hall (Splunk)

Panevo Services Ltd.
