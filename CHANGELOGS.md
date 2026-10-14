# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.3] - 2026-10-14

- Declare `requests` and `six` as dependencies. Previously they had to be installed separately, otherwise importing the package failed
- Declare the supported Python versions (3.8 and newer) and add Python 3.13 and 3.14
- Move the package configuration from `setup.py` to `pyproject.toml`
- Publish releases to PyPI using trusted publishing

## [1.0.0] - 2024-07-17

- [#2](https://github.com/panevo/notificationhubs-rest-python/pull/2) Initial release of the Notification Hubs REST wrapper for Python.
- [#3](https://github.com/panevo/notificationhubs-rest-python/pull/3) Update SECURITY.md with information about the repository.
- [#4](https://github.com/panevo/notificationhubs-rest-python/pull/4) Update README.md with information about the repository.
