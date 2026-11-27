"""Tests for Java discovery and version parsing without a system Java installation (M1-BE-05)."""

import sys
from pathlib import Path

import pytest

from mcserver.application.errors import InvalidJavaExecutable, JavaNotFound
from mcserver.infrastructure.java_runtime import JavaRuntimeResolver, JavaRuntimeSource, parse_java_major


@pytest.mark.parametrize(
    ("output", "major"),
    [
        ('java version "1.8.0_401"\nJava(TM) SE Runtime Environment', 8),
        ('openjdk version "17.0.10" 2024-01-16', 17),
        ('openjdk version "21.0.2" 2024-01-16 LTS', 21),
        ('java version "25.0.2" 2026-01-20 LTS', 25),
        ('openjdk version "25" 2025-09-16', 25),
        ('openjdk version "16-ea"', 16),
        ("no version here", None),
    ],
)
def test_parses_java_major_versions(output: str, major: int | None) -> None:
    assert parse_java_major(output) == major


def resolver(
    versions: dict[str, int],
    *,
    which: str | None = None,
    env: dict[str, str] | None = None,
    roots: tuple[Path, ...] = (),
    bundled: tuple[Path, ...] = (),
) -> JavaRuntimeResolver:
    return JavaRuntimeResolver(
        bundled,
        probe=lambda path: versions.get(path.name if path.name in versions else str(path)),
        environ=env or {},
        which=lambda _name: which,
        install_roots=roots,
    )


def test_prefers_a_valid_bundled_runtime(tmp_path: Path) -> None:
    bundled_java = tmp_path / "bundled-java.exe"

    runtime = resolver({"bundled-java.exe": 21}, bundled=(bundled_java,)).resolve()

    assert runtime.executable == bundled_java.resolve()
    assert runtime.source is JavaRuntimeSource.BUNDLED
    assert runtime.major_version == 21


def test_raises_when_no_runtime_is_usable(tmp_path: Path) -> None:
    with pytest.raises(JavaNotFound):
        resolver({}, bundled=(tmp_path / "missing-java",)).resolve()


def test_search_order_is_java_home_then_path_then_installed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    installed = tmp_path / "Eclipse Adoptium" / "jdk-21" / "bin"
    installed.mkdir(parents=True)
    home_java = str(home / "bin" / ("java.exe" if sys.platform == "win32" else "java"))
    versions = {"which-java": 17, str(installed / "java.exe"): 21, str(installed / "java"): 21}
    found = resolver(
        versions | {home_java: 11},
        which="which-java",
        env={"JAVA_HOME": str(home)},
        roots=(tmp_path / "Eclipse Adoptium",),
    )

    assert found.find().source == "java_home"
    assert found.find(17).source == "path"
    assert found.find(21).source == "installed"


def test_falls_back_to_the_first_runtime_when_none_meets_the_minimum() -> None:
    found = resolver({"which-java": 17}, which="which-java").find(21)

    assert found.major_version == 17
    assert found.source == "path"


def test_a_configured_executable_wins_and_can_be_cleared(tmp_path: Path) -> None:
    chosen = tmp_path / "my-java.exe"
    java = resolver({"my-java.exe": 8, "which-java": 21}, which="which-java")

    installation = java.configure(str(chosen))

    assert installation is not None and installation.major_version == 8
    assert java.configured_executable == str(chosen)
    assert java.find(21).source == "configured"  # the user's choice is honoured even if too old
    java.configure(None)
    assert java.find(21).source == "path"


def test_an_unusable_configured_executable_is_rejected(tmp_path: Path) -> None:
    java = resolver({})

    with pytest.raises(InvalidJavaExecutable):
        java.configure(str(tmp_path / "notepad.exe"))

    assert java.configured_executable is None


def test_java_installed_later_is_found_without_a_new_resolver() -> None:
    versions: dict[str, int] = {}
    java = resolver(versions, which="which-java")
    with pytest.raises(JavaNotFound):
        java.find()

    versions["which-java"] = 21

    assert java.find().major_version == 21
