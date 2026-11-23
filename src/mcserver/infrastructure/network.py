"""This computer's address on the local network (M3-GUI-05)."""

from __future__ import annotations

import ipaddress
import socket

# A documentation address (RFC 5737): connecting a UDP socket only picks the outgoing interface; nothing is sent.
_PROBE_TARGET = ("192.0.2.1", 9)


def _usable(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return parsed.version == 4 and not (parsed.is_loopback or parsed.is_link_local or parsed.is_unspecified)


def lan_ipv4_address() -> str | None:
    """Return the IPv4 address other computers on the LAN can reach, or ``None`` when there is none."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(_PROBE_TARGET)
            address = str(probe.getsockname()[0])
        if _usable(address):
            return address
    except OSError:
        pass
    try:
        candidates = socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        return None
    return next((address for address in candidates if _usable(address)), None)
