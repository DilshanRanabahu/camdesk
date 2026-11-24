from __future__ import annotations

import pytest

from camdesk.core import messages
from camdesk.core.validation import AddressError, parse_address


@pytest.mark.parametrize(
    ("address", "port", "expected"),
    [
        ("192.168.8.105", "8080", ("192.168.8.105", 8080)),
        ("  192.168.8.105  ", "", ("192.168.8.105", 8080)),  # default port
        ("192.168.8.105", "9000", ("192.168.8.105", 9000)),
        ("http://192.168.8.105:8080", "1234", ("192.168.8.105", 8080)),  # as IP Webcam shows it
        ("https://192.168.8.105:8443/", "", ("192.168.8.105", 8443)),
        ("192.168.8.105:8081", "8080", ("192.168.8.105", 8081)),  # port in the address wins
        ("phone.local", "8080", ("phone.local", 8080)),
        ("[2405:6b00::1]:8080", "", ("2405:6b00::1", 8080)),
    ],
)
def test_valid_addresses(address: str, port: str, expected: tuple[str, int]) -> None:
    assert parse_address(address, port) == expected


@pytest.mark.parametrize(
    ("address", "port", "message"),
    [
        ("", "8080", messages.ADDRESS_EMPTY),
        ("   ", "8080", messages.ADDRESS_EMPTY),
        ("192.168.1", "8080", messages.ADDRESS_INVALID),
        ("192.168.1.300", "8080", messages.ADDRESS_INVALID),
        ("not an ip", "8080", messages.ADDRESS_INVALID),
        ("192.168.8.105", "abc", messages.PORT_INVALID),
        ("192.168.8.105", "70000", messages.PORT_INVALID),
        ("192.168.8.105", "0", messages.PORT_INVALID),
        ("192.168.8.105:99999", "", messages.PORT_INVALID),
    ],
)
def test_invalid_addresses(address: str, port: str, message: str) -> None:
    with pytest.raises(AddressError) as info:
        parse_address(address, port)
    assert str(info.value) == message
