"""Check what the user typed on the connect screen. Pure functions, easy to test."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

from camdesk.core import messages
from camdesk.core.models import DEFAULT_PORT

_HOSTNAME = re.compile(
    r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$",
    re.I,
)


class AddressError(ValueError):
    """The message is ready to show to the user."""


def parse_address(address: str, port: str = "") -> tuple[str, int]:
    """Return (host, port) from the address and port fields.

    Accepts what IP Webcam shows, pasted as-is: "http://192.168.8.105:8080" or
    "192.168.8.105:8080". A port inside the address wins over the port field.
    """
    text = address.strip()
    if not text:
        raise AddressError(messages.ADDRESS_EMPTY)
    if "://" not in text:
        text = "//" + text  # let urlsplit find host and port
    try:
        parts = urlsplit(text)
        host = parts.hostname or ""
        url_port = parts.port
    except ValueError as exc:  # e.g. port out of range inside the URL
        raise AddressError(messages.PORT_INVALID) from exc
    if not host or not _is_host(host):
        raise AddressError(messages.ADDRESS_INVALID)
    if url_port is not None:
        return host, url_port
    return host, _parse_port(port)


def _parse_port(text: str) -> int:
    text = text.strip()
    if not text:
        return DEFAULT_PORT
    if not text.isdigit() or not 1 <= int(text) <= 65535:
        raise AddressError(messages.PORT_INVALID)
    return int(text)


def _is_host(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    if re.fullmatch(r"[\d.]+", host):
        return False  # looks like a broken IPv4 address, e.g. 192.168.1
    return bool(_HOSTNAME.match(host))
