# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - Unreleased

- Each `AzureNotificationHub` object keeps its own credentials, and its requests and SAS tokens follow its `Endpoint`, `HubName`, `SasKeyName` and `SasKeyValue` attributes. Previously all objects in a process shared the credentials of the one created last
- Connection strings are read as key/value pairs in any order, and a trailing `;` is allowed
- Creating a hub without a hub name raises a `ValueError`. Previously it failed with a `TypeError` on the first send
- Requests use `api-version=2020-06`
- Requests have a default timeout (10 seconds to connect, 30 seconds to read). Throttled requests (429) and transient errors (408, 500, 503, 504, and 403 with `Retry-After`) are retried up to 3 times with exponential backoff, honouring `Retry-After` up to 60 seconds. Use the `timeout` and `max_retries` arguments to change this
- Error responses raise `NotificationHubError`, a subclass of `Exception`, with the status code and the service's error code and detail. HTTP 200 and 201 both count as success. Timeouts and connection errors raise the `requests` exceptions
- Debug sends raise on failure like other sends, and their output goes to the `notificationhubs_rest_python` logger instead of being printed. The SAS token is never logged
- The headers returned by the send methods no longer contain the SAS token
- SAS tokens are reused until they are close to expiring, and are available as `generate_sas_token()`. The private `_AzureNotificationHub__generate_sas_token()` keeps working
- Add type hints
- `send_google_notification` sends Firebase Cloud Messaging (FCM) v1 notifications (the `fcmV1` format), because Notification Hubs stopped supporting the legacy GCM/FCM API on 2024-06-20, and Google has since shut it down. The payload must use the FCM v1 format, wrapped in a `message` object, otherwise it raises a `ValueError`
- `AzureNotification` accepts the `fcmV1` format, and raises a `ValueError` for the retired `gcm` and `windowsphone` formats
- `send_windows_phone_notification` raises `NotImplementedError`, because Microsoft no longer supports MPNS
- Scheduled sends send the time in the correct format and in UTC. A time without a timezone is taken as UTC
- `send_windows_notification` sets the `X-WNS-Type` header from the root element of the XML payload, also when it has attributes, such as `<badge value="1"/>`
- Drop support for Python 3.8 (end of life) and the dependency on `six`
- Whitespace around the parts of a connection string is ignored, such as a trailing newline
- A `Retry-After` header that is not a finite number is ignored, and the default backoff is used instead. A `Retry-After` date without a timezone is taken as UTC
- Notifications are sent encoded as UTF-8. Previously, with urllib3 1.x, Windows notifications were sent encoded as Latin-1, and failed with a `UnicodeEncodeError` for characters outside Latin-1
- An empty set of tags, or a set with an empty tag, raises a `ValueError`. Previously an empty set, or a set with only an empty tag, sent the notification to all devices
- Tags that are not a string or a set, such as a list, raise a `TypeError`
- `NotificationHubError` keeps plain-text error responses as its detail, such as `Access denied. Invalid SAS token.` for a wrong key
- Panevo now maintains the code. Update the README for 2.0, and the security policy for reporting vulnerabilities through GitHub's private vulnerability reporting

## [1.0.3] - 2026-10-14

- Declare `requests` and `six` as dependencies. Previously they had to be installed separately, otherwise importing the package failed
- Declare the supported Python versions (3.8 and newer) and add Python 3.13 and 3.14
- Move the package configuration from `setup.py` to `pyproject.toml`
- Publish releases to PyPI using trusted publishing

## [1.0.0] - 2024-07-17

- [#2](https://github.com/panevo/notificationhubs-rest-python/pull/2) Initial release of the Notification Hubs REST wrapper for Python.
- [#3](https://github.com/panevo/notificationhubs-rest-python/pull/3) Update SECURITY.md with information about the repository.
- [#4](https://github.com/panevo/notificationhubs-rest-python/pull/4) Update README.md with information about the repository.
