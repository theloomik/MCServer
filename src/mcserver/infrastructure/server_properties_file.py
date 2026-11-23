"""Read and update ``server.properties`` without disturbing what the user or Minecraft wrote (M3-BE-01).

* Reading follows Java properties rules (``=`` or ``:`` separators, ``\\uXXXX``
  and backslash escapes, ``#``/``!`` comments). Files are read as UTF-8, or as
  Latin-1 when they are not valid UTF-8 (older servers wrote Latin-1).
* Writing changes only the lines of changed keys and appends new keys at the
  end. Every other line, comments and line endings stay byte-for-byte the same.
  Values are written the way Java's ``Properties.store`` does (non-ASCII as
  ``\\uXXXX``), so every server type reads them back correctly.
* Writes go through a temporary file and an atomic replace.
"""

from __future__ import annotations

import errno
import os
import socket
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from mcserver.application.ports import ServerConfigurationRepository
from mcserver.application.server_properties import ServerPropertiesDocument

PROPERTIES_FILE = "server.properties"
_HEADER = "#Minecraft server properties (created by MCServer)\n"


@dataclass(frozen=True, slots=True)
class PropertiesDocument:
    """Decoded ``key → value`` pairs in file order; ``exists`` is false before the first start."""

    values: dict[str, str]
    exists: bool


def _decode(text: str) -> str:
    result: list[str] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character != "\\" or index + 1 >= len(text):
            result.append(character)
            index += 1
            continue
        following = text[index + 1]
        if following == "u" and index + 6 <= len(text):
            try:
                result.append(chr(int(text[index + 2 : index + 6], 16)))
                index += 6
                continue
            except ValueError:
                pass
        result.append({"t": "\t", "n": "\n", "r": "\r", "f": "\f"}.get(following, following))
        index += 2
    return "".join(result)


def _encode(value: str) -> str:
    """Escape like ``Properties.store``: backslash, separators, comment marks, leading space, non-ASCII."""
    out: list[str] = []
    for position, character in enumerate(value):
        if character == "\\":
            out.append("\\\\")
        elif character in "=:#!":
            out.append("\\" + character)
        elif character == " " and position == 0:
            out.append("\\ ")
        elif ord(character) < 0x20 or ord(character) > 0x7E:
            out.append(f"\\u{ord(character):04x}")
        else:
            out.append(character)
    return "".join(out)


def _split(line: str) -> tuple[str, str] | None:
    """Return the raw (key, value) of a property line, or ``None`` for comments and blank lines."""
    stripped = line.lstrip(" \t\f")
    if not stripped or stripped[0] in "#!" or stripped in ("\n", "\r\n", "\r"):
        return None
    body = stripped.rstrip("\r\n")
    index = 0
    while index < len(body):
        character = body[index]
        if character == "\\":
            index += 2
            continue
        if character in "=: \t\f":
            break
        index += 1
    key = body[:index]
    rest = body[index:].lstrip(" \t\f")
    if rest[:1] in ("=", ":"):
        rest = rest[1:].lstrip(" \t\f")
    return _decode(key), rest


def _read_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def read_properties(path: Path) -> PropertiesDocument:
    """Read ``path``; a missing or unreadable file gives an empty document."""
    try:
        text, _encoding = _read_text(path)
    except FileNotFoundError:
        return PropertiesDocument({}, False)
    except OSError:
        return PropertiesDocument({}, path.exists())
    values: dict[str, str] = {}
    for line in text.splitlines(keepends=True):
        parsed = _split(line)
        if parsed is not None:
            values[parsed[0]] = _decode(parsed[1])
    return PropertiesDocument(values, True)


def write_properties(path: Path, changes: dict[str, str]) -> None:
    """Apply ``changes`` (already validated) to ``path`` atomically; create the file if needed."""
    try:
        text, encoding = _read_text(path)
    except FileNotFoundError:
        text, encoding = _HEADER, "utf-8"
    lines = text.splitlines(keepends=True)
    ending = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    pending = dict(changes)
    output: list[str] = []
    for line in lines:
        parsed = _split(line)
        if parsed is not None and parsed[0] in pending:
            line_ending = line[len(line.rstrip("\r\n")) :] or ending
            output.append(f"{parsed[0]}={_encode(pending.pop(parsed[0]))}{line_ending}")
        else:
            output.append(line)
    if output and not output[-1].endswith(("\n", "\r")):
        output[-1] += ending
    output.extend(f"{key}={_encode(value)}{ending}" for key, value in pending.items())
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".server.properties.", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding=encoding, newline="") as handle:
            handle.write("".join(output))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def port_in_use(host: str, port: int) -> bool:
    """Return whether a TCP listener on ``host:port`` would fail (another program holds the port)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((host or "0.0.0.0", port))  # nosec B104 - only a probe, closed at once
        except OSError as error:
            # Only "address in use" / "access denied (exclusive use)" mean another program holds it;
            # an unknown server-ip is a different problem that the server itself reports.
            in_use_codes = {errno.EADDRINUSE, errno.EACCES, 10048, 10013}
            return error.errno in in_use_codes or getattr(error, "winerror", None) in in_use_codes
    return False


class FileServerPropertiesStore:
    """Implement ``ServerPropertiesStore`` for servers directly inside the servers root."""

    def __init__(self, servers_directory: Path, repository: ServerConfigurationRepository) -> None:
        """Find each server's folder through ``repository``."""
        self._root = servers_directory.resolve()
        self._repository = repository

    def read(self, server_id: str) -> ServerPropertiesDocument:
        """Return the decoded properties of ``server_id``."""
        document = read_properties(self._path(server_id))
        return ServerPropertiesDocument(document.values, document.exists)

    def write(self, server_id: str, changes: Mapping[str, str]) -> None:
        """Apply validated ``changes`` atomically."""
        write_properties(self._path(server_id), dict(changes))

    def _path(self, server_id: str) -> Path:
        directory = (self._root / self._repository.get(server_id).directory).resolve()
        if directory.parent != self._root:
            # Imported here: server_configuration imports this module for its launch checks.
            from mcserver.infrastructure.server_configuration import ServerConfigurationError

            raise ServerConfigurationError(f"Server '{server_id}' directory resolves outside the managed root.")
        return directory / PROPERTIES_FILE
