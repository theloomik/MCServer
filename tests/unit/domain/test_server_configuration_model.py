"""Tests for the server configuration domain model."""

import pytest

from mcserver.domain.errors import InvalidServerConfiguration
from mcserver.domain.server_configuration import MAX_MEMORY_MB, MIN_MEMORY_MB, ServerConfiguration


def make(**overrides: object) -> ServerConfiguration:
    values: dict[str, object] = {
        "server_id": "survival",
        "directory": "survival",
        "jar_file": "paper.jar",
        "memory_mb": 2048,
    }
    values.update(overrides)
    return ServerConfiguration(**values)  # type: ignore[arg-type]


def test_accepts_valid_configuration() -> None:
    configuration = make(server_id="My Server 1", directory="My Server 1", jar_file="Paper-1.21.JAR")

    assert configuration.server_id == "My Server 1"


@pytest.mark.parametrize("memory", [MIN_MEMORY_MB, MAX_MEMORY_MB])
def test_accepts_memory_bounds(memory: int) -> None:
    assert make(memory_mb=memory).memory_mb == memory


@pytest.mark.parametrize(
    "name",
    ["", ".", "..", " lead", "trail ", "dot.", "a/b", "a\\b", "a:b", "a*b", "tab\tname", "CON", "nul.txt", "Com1", 5],
)
def test_rejects_unsafe_server_id_and_directory(name: object) -> None:
    with pytest.raises(InvalidServerConfiguration, match="identifier"):
        make(server_id=name)
    with pytest.raises(InvalidServerConfiguration, match="directory"):
        make(directory=name)


@pytest.mark.parametrize("jar", ["paper.zip", "paper", "../paper.jar", "dir/paper.jar", "", ".jar."])
def test_rejects_invalid_jar_file(jar: str) -> None:
    with pytest.raises(InvalidServerConfiguration, match="JAR"):
        make(jar_file=jar)


@pytest.mark.parametrize("memory", [MIN_MEMORY_MB - 1, MAX_MEMORY_MB + 1, 0, -1])
def test_rejects_memory_out_of_range(memory: int) -> None:
    with pytest.raises(InvalidServerConfiguration, match="between"):
        make(memory_mb=memory)


@pytest.mark.parametrize("memory", [True, 2048.0, "2048", None])
def test_rejects_non_integer_memory(memory: object) -> None:
    with pytest.raises(InvalidServerConfiguration, match="integer"):
        make(memory_mb=memory)
