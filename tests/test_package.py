"""The installed package."""

from importlib import resources

import notificationhubs_rest_python


def test_public_names():
    namespace = {}
    exec("from notificationhubs_rest_python import *", namespace)

    assert {name for name in namespace if not name.startswith("__")} == {
        "AzureNotification",
        "AzureNotificationHub",
        "NotificationHubError",
    }


def test_type_hints_are_shipped():
    assert resources.files(notificationhubs_rest_python).joinpath("py.typed").is_file()
