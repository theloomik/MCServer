"""Download dialog and the Create server dialog's Download button (M3-GUI-06)."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from fakes import InMemoryRepository, MemoryFilesystem, creation_for, management_for
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from mcserver.application.server_catalog import (
    CatalogUnavailable,
    CatalogVersion,
    DownloadCancelled,
    ServerDownload,
    ServerJarCatalog,
    ServerType,
)
from mcserver.presentation.controllers.jar_catalog import JarCatalogController
from mcserver.presentation.controllers.server_creation import ServerCreationController
from mcserver.presentation.dialogs.create_server_dialog import CreateServerDialog
from mcserver.presentation.dialogs.download_jar_dialog import DownloadJarDialog
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.workers import BackgroundRunner

MESSAGES = messages_for()


class Source:
    def __init__(self, server_type: ServerType, *versions: tuple[str, bool], fail: bool = False) -> None:
        self.server_type = server_type
        self.items = tuple(CatalogVersion(server_type, version, stable) for version, stable in versions)
        self.fail = fail

    def versions(self) -> tuple[CatalogVersion, ...]:
        if self.fail:
            raise CatalogUnavailable("no connection (getaddrinfo failed)")
        return self.items

    def resolve(self, version: str) -> ServerDownload:
        return ServerDownload(
            self.server_type,
            version,
            f"{self.server_type.value}-{version}.jar",
            "https://fill-data.papermc.io/x.jar",
            50 * 1024 * 1024,
            "sha256",
            "0" * 64,
            21,
            stable=version != "1.21.10",
        )


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.gate: Event | None = None
        self.fetched: list[str] = []

    def fetch(self, download: ServerDownload, progress, cancelled) -> str:  # type: ignore[no-untyped-def]
        if self.gate is not None:
            while not self.gate.wait(0.01):
                if cancelled():
                    raise DownloadCancelled(download.file_name)
        progress(10, 20)
        path = self.root / download.file_name
        path.write_bytes(b"jar")
        self.fetched.append(download.version)
        return str(path)


def make(
    qtbot: QtBot, tmp_path: Path, *, paper_fails: bool = False
) -> tuple[DownloadJarDialog, JarCatalogController, Store]:
    store = Store(tmp_path)
    catalog = ServerJarCatalog(
        {
            ServerType.PAPER: Source(
                ServerType.PAPER, ("26.1-rc-2", False), ("1.21.11", True), ("1.21.10", True), fail=paper_fails
            ),
            ServerType.VANILLA: Source(ServerType.VANILLA, ("1.21.11", True)),
        },
        store,  # type: ignore[arg-type]
    )
    background = BackgroundRunner()
    controller = JarCatalogController(catalog, background)
    dialog = DownloadJarDialog(controller, MESSAGES)
    qtbot.addWidget(dialog)
    return dialog, controller, store


def wait_resolved(qtbot: QtBot, controller: JarCatalogController) -> None:
    qtbot.waitUntil(lambda: controller.state.download is not None)


def test_newest_stable_version_is_selected_and_described(qtbot: QtBot, tmp_path: Path) -> None:
    dialog, controller, _store = make(qtbot, tmp_path)
    wait_resolved(qtbot, controller)
    assert [dialog.version_list.item(row).text() for row in range(dialog.version_list.count())] == [
        "1.21.11",
        "1.21.10",
    ]
    assert controller.state.selected == "1.21.11"
    assert "paper-1.21.11.jar, about 50 MB." in dialog.details.text()
    assert MESSAGES.text("catalog.java", java=21) in dialog.details.text()
    assert dialog.download_button.isEnabled()

    dialog.version_list.setCurrentRow(1)
    qtbot.waitUntil(lambda: controller.state.download is not None and controller.state.download.version == "1.21.10")
    assert MESSAGES.text("catalog.experimental_build") in dialog.details.text()


def test_test_versions_and_server_type_can_be_switched(qtbot: QtBot, tmp_path: Path) -> None:
    dialog, controller, _store = make(qtbot, tmp_path)
    wait_resolved(qtbot, controller)
    dialog.unstable_check.setChecked(True)
    qtbot.waitUntil(lambda: dialog.version_list.count() == 3)
    assert dialog.version_list.item(0).text() == MESSAGES.text("catalog.version.unstable", version="26.1-rc-2")
    dialog.type_combo.setCurrentIndex(1)
    qtbot.waitUntil(
        lambda: controller.state.server_type is ServerType.VANILLA and controller.state.download is not None
    )
    assert controller.state.download is not None and controller.state.download.file_name == "vanilla-1.21.11.jar"


def test_download_returns_the_verified_path(qtbot: QtBot, tmp_path: Path) -> None:
    dialog, controller, store = make(qtbot, tmp_path)
    wait_resolved(qtbot, controller)
    dialog.download_button.click()
    qtbot.waitUntil(lambda: dialog.path is not None)
    assert dialog.path == str(tmp_path / "paper-1.21.11.jar") and store.fetched == ["1.21.11"]
    assert dialog.result() == DownloadJarDialog.DialogCode.Accepted


def test_closing_during_a_download_cancels_it_first(qtbot: QtBot, tmp_path: Path) -> None:
    dialog, controller, store = make(qtbot, tmp_path)
    store.gate = Event()
    wait_resolved(qtbot, controller)
    dialog.show()
    dialog.download_button.click()
    qtbot.waitUntil(lambda: controller.state.downloading)
    dialog.reject()
    assert dialog.isVisible()  # stays open until the download has stopped
    qtbot.waitUntil(lambda: not controller.state.downloading)
    assert controller.state.error is None and dialog.path is None and store.fetched == []
    dialog.reject()
    assert not dialog.isVisible()


def test_offline_catalog_shows_the_reason(qtbot: QtBot, tmp_path: Path) -> None:
    dialog, controller, _store = make(qtbot, tmp_path, paper_fails=True)
    qtbot.waitUntil(lambda: controller.state.error is not None)
    assert dialog.error_label.text() == MESSAGES.text(
        "errors.catalog_unavailable", reason="no connection (getaddrinfo failed)"
    )
    assert not dialog.download_button.isEnabled()


def test_create_dialog_uses_the_downloaded_jar(qtbot: QtBot, tmp_path: Path) -> None:
    repository = InMemoryRepository()
    controller = ServerCreationController(
        creation_for(repository, MemoryFilesystem()), management_for(repository), BackgroundRunner()
    )
    downloaded = str(tmp_path / ".downloads" / "paper-1.21.11-132.jar")

    def download(_parent: QWidget) -> str | None:
        return downloaded

    dialog = CreateServerDialog(controller, MESSAGES, download_jar=download)
    qtbot.addWidget(dialog)
    assert not dialog.download_button.isHidden()
    dialog.download_button.click()
    assert dialog.form().source_jar == downloaded and dialog.jar_edit.text() == "paper-1.21.11-132.jar"

    plain = CreateServerDialog(controller, MESSAGES)
    qtbot.addWidget(plain)
    assert plain.download_button.isHidden()  # no catalog: only Browse
