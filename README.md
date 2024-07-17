# Notification Hubs REST wrapper for Python

This is an implementation of a REST wrapper for sending notifications with Notification Hubs using the [REST APIs of Notification Hubs](http://msdn.microsoft.com/en-us/library/dn495827.aspx) from a Python back-end. The useage of this code is officially recommended by Microsoft in the [documentation](https://learn.microsoft.com/en-us/azure/notification-hubs/notification-hubs-python-push-notification-tutorial#client-interface).

Panevo Services Ltd. is maintaining this repo for the sole purpose of publishing this Notification Hubs REST wrapper to PyPI. In this regard, Panevo will only be pulling upstream changes from the original repo and not making any further changes to the codebase.

This repository is a fork of Microsoft's [Azure Notification Hub Samples Repository](https://github.com/Azure/azure-notificationhubs-samples).

## How to use the code above

Install the package

```
pip install notificationhubs-rest-python
```

Detailed readme is available here -
http://azure.microsoft.com/en-us/documentation/articles/notification-hubs-python-backend-how-to/

## Requirements

This package requires Python 3.8+ and version 2.25.0+ of the `requests` package.

## Registration management

For registration management you have to follow the content formats shown in the [REST APIs of Notification Hubs](http://msdn.microsoft.com/en-us/library/dn495827.aspx), and probably do some xml parsing is case of GETs. Be warned that element order is important and things will not work if the element are out of order.

## Notes

This code is provided as-is with no guarantees.

## Contributors

Adrian Hall (Splunk)

Panevo Services Ltd.
