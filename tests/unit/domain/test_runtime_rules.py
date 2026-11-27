"""Tests for readiness detection, verified Java requirements and failure diagnosis (pure domain)."""

import pytest

from mcserver.domain.diagnostics import FailureHint, diagnose
from mcserver.domain.java_requirements import (
    HIGHEST_VERIFIED_VERSION,
    parse_minecraft_version,
    required_java_major,
)
from mcserver.domain.readiness import is_ready_line


@pytest.mark.parametrize(
    "line",
    [
        '[12:00:00] [Server thread/INFO]: Done (3.456s)! For help, type "help"',  # Vanilla / Paper
        '[12:00:00 INFO]: Done (12,5s)! For help, type "help"',  # comma decimal separator
        '[Server thread/INFO] [minecraft/DedicatedServer]: Done (20.1s)! For help, type "help" or "?"',  # Forge
        '\x1b[32m[12:00:00 INFO]: Done (3.4s)! For help, type "help"\x1b[0m',  # ANSI colours
    ],
)
def test_ready_lines_of_common_servers_match(line: str) -> None:
    assert is_ready_line(line)


@pytest.mark.parametrize(
    "line",
    [
        "[Server thread/INFO]: Preparing spawn area: 97%",
        "<Steve> Done (3.4s)! For help",  # a player chat line without the full marker
        "Done preparing level",
        "",
    ],
)
def test_other_lines_do_not_match(line: str) -> None:
    assert not is_ready_line(line)


def test_extra_rules_can_be_added_for_new_server_types() -> None:
    assert is_ready_line("Proxy ready", rules=(lambda text: text == "Proxy ready",))


@pytest.mark.parametrize(
    ("text", "major"),
    [
        ("1.8.9", 8),
        ("1.16.5", 8),
        ("1.17", 16),
        ("1.17.1", 16),
        ("1.18", 17),
        ("1.20.4", 17),
        ("1.20.5", 21),
        ("1.21.11", 21),
        ("26.1", 25),
        ("26.3", 25),
    ],
)
def test_verified_versions_map_to_their_java_major(text: str, major: int) -> None:
    assert required_java_major(parse_minecraft_version(text)) == major


@pytest.mark.parametrize("text", ["26.4", "27.1", "26.3.1-rc1", "24w14a", "1.21-pre1", "custom", ""])
def test_unverified_or_unparseable_versions_have_no_assumed_requirement(text: str) -> None:
    assert required_java_major(parse_minecraft_version(text)) is None


def test_the_verified_bound_is_explicit() -> None:
    assert HIGHEST_VERIFIED_VERSION == (26, 3)
    assert required_java_major((26, 3, 0)) == 25
    assert required_java_major((26, 3, 1)) is None


@pytest.mark.parametrize(
    ("lines", "hint"),
    [
        (["[main/WARN]: You need to agree to the EULA in order to run the server."], FailureHint.EULA_NOT_ACCEPTED),
        (["**** FAILED TO BIND TO PORT!"], FailureHint.PORT_IN_USE),
        (["java.net.BindException: Address already in use: bind"], FailureHint.PORT_IN_USE),
        (
            [
                "java.lang.UnsupportedClassVersionError: net/minecraft/bundler/Main has been compiled by a more recent version"
            ],
            FailureHint.JAVA_TOO_OLD,
        ),
        (["Exception in thread main java.lang.OutOfMemoryError: Java heap space"], FailureHint.OUT_OF_MEMORY),
        (["Error: Could not reserve enough space for 8388608KB object heap"], FailureHint.OUT_OF_MEMORY),
        (["Error: Invalid or corrupt jarfile server.jar"], FailureHint.CORRUPT_JAR),
        (["Stopping server"], FailureHint.UNKNOWN),
        ([], FailureHint.UNKNOWN),
    ],
)
def test_common_failures_are_recognised(lines: list[str], hint: FailureHint) -> None:
    assert diagnose(lines) is hint
