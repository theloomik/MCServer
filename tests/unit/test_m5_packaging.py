"""M5: one version source, Windows identity, and the build files agreeing with the app."""

from __future__ import annotations

import re
import struct
import subprocess
import tomllib
from pathlib import Path

import pytest

import mcserver
from mcserver.infrastructure import java_runtime
from tools import build_windows

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = (ROOT / "packaging" / "windows" / "MCServer.iss").read_text(encoding="utf-8")
SPEC = (ROOT / "packaging" / "windows" / "MCServer.spec").read_text(encoding="utf-8")


def test_the_version_has_one_source() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in project["project"] and project["project"]["dynamic"] == ["version"]
    assert project["tool"]["hatch"]["version"]["path"] == "src/mcserver/__init__.py"
    identity = build_windows.read_identity()
    assert identity.version == mcserver.__version__
    assert (identity.name, identity.publisher, identity.homepage) == (
        mcserver.APP_NAME,
        mcserver.PUBLISHER,
        mcserver.HOMEPAGE,
    )


@pytest.mark.parametrize(
    ("version", "numbers"),
    [("2.0.0a1", (2, 0, 0, 0)), ("2.1", (2, 1, 0, 0)), ("2.0.3rc2", (2, 0, 3, 0)), ("1.2.3.4.5", (1, 2, 3, 4))],
)
def test_windows_file_versions_are_numeric(version: str, numbers: tuple[int, ...]) -> None:
    assert build_windows.file_version(version) == numbers


def test_file_version_rejects_text() -> None:
    with pytest.raises(ValueError):
        build_windows.file_version("dev")


def test_the_icon_file_holds_every_size(qapp: object, tmp_path: Path) -> None:
    images = build_windows.draw_images(tmp_path)
    data = Path(images["icon"]).read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, len(build_windows.ICO_SIZES))
    sizes = []
    for index in range(count):
        width, _height, _colors, _reserved, _planes, bits, length, offset = struct.unpack_from(
            "<BBBBHHII", data, 6 + 16 * index
        )
        assert bits == 32 and data[offset : offset + 8] == b"\x89PNG\r\n\x1a\n" and offset + length <= len(data)
        sizes.append(width or 256)
    assert sizes == sorted(build_windows.ICO_SIZES)
    for listed in (images["wizard_small"], images["wizard_large"]):
        assert all(Path(path).is_file() for path in listed.split(","))


def test_the_version_resource_names_mcserver() -> None:
    from PyInstaller.utils.win32.versioninfo import VSVersionInfo  # noqa: F401 (the generated text uses it)

    text = build_windows.version_resource(build_windows.read_identity())
    namespace: dict[str, object] = {}
    exec("from PyInstaller.utils.win32.versioninfo import *", namespace)  # noqa: S102  # nosec B102
    resource = eval(text, namespace)  # noqa: S307  # nosec B307 (our own generated text)
    strings = {entry.name: entry.val for entry in resource.kids[0].kids[0].kids}
    assert strings["ProductName"] == strings["FileDescription"] == "MCServer"
    assert strings["ProductVersion"] == mcserver.__version__
    assert strings["OriginalFilename"] == "MCServer.exe"
    assert strings["LegalCopyright"] == mcserver.COPYRIGHT


def test_the_installer_agrees_with_the_app() -> None:
    from mcserver.presentation import app

    mutexes = re.search(r"^AppMutex=(.+)$", INSTALLER, re.MULTILINE)
    assert mutexes is not None and app.RUNNING_MUTEX in mutexes.group(1).split(",")
    assert INSTALLER.count(f'AppUserModelID: "{app.APP_USER_MODEL_ID}"') == 2  # Start menu and desktop shortcuts
    assert "PrivilegesRequired=lowest" in INSTALLER  # no administrator rights by default
    assert "CloseApplications=no" in INSTALLER  # the user closes MCServer, so servers stop properly


def test_uninstalling_never_removes_user_data() -> None:
    assert re.search(r"^\[UninstallDelete\]", INSTALLER, re.MULTILINE) is None
    install_delete = INSTALLER.split("[InstallDelete]", 1)[1].split("\n[", 1)[0]
    targets = re.findall(r'Name: "([^"]+)"', install_delete)
    assert targets == ["{app}\\_internal"]  # only the bundled libraries, inside the installation folder


def test_the_spec_bundles_the_translations() -> None:
    assert '"i18n" / "locales"' in SPEC and "mcserver/presentation/i18n/locales" in SPEC
    assert "console=False" in SPEC
    assert (ROOT / "src" / "mcserver" / "presentation" / "i18n" / "locales" / "uk.json").is_file()


def test_java_is_probed_without_a_console_window(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []
    java = tmp_path / "java.exe"
    java.write_bytes(b"")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 0, "", 'openjdk version "21.0.2"')

    monkeypatch.setattr(java_runtime, "run", fake_run)
    assert java_runtime.probe_java_version(java) == 21
    assert calls[0]["creationflags"] == java_runtime.NO_CONSOLE_WINDOW
