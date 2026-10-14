from typing import Optional


def parse_connection_string(connection_string: Optional[str]) -> tuple[str, str, str]:
    """Return the endpoint, key name and key from a Notification Hubs connection string.

    The parts can come in any order and a trailing ``;`` is allowed. The ``sb://`` endpoint is
    returned as ``https://`` with a trailing ``/``.
    """
    if not isinstance(connection_string, str):
        raise ValueError("Invalid connection string: expected a string")

    parts = {}
    for part in connection_string.split(";"):
        if not part:
            continue
        name, separator, value = part.partition("=")
        if not separator:
            raise ValueError("Invalid connection string: expected name=value parts separated by ';'")
        parts[name.strip().lower()] = value.strip()

    missing = [name for name in ("Endpoint", "SharedAccessKeyName", "SharedAccessKey") if name.lower() not in parts]
    if missing:
        raise ValueError("Invalid connection string: missing " + ", ".join(missing))

    endpoint = parts["endpoint"]
    if endpoint.startswith("sb://"):
        endpoint = "https://" + endpoint[len("sb://") :]
    if endpoint and not endpoint.endswith("/"):
        endpoint += "/"
    return endpoint, parts["sharedaccesskeyname"], parts["sharedaccesskey"]
