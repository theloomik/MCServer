"""Offscreen Qt tests for the main window's server list and details panel."""

from pathlib import Path

from fakes import InMemoryRepository, coordinator, services_for
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.controllers.server_list import ServerStatus
from mcserver.presentation.i18n import en, messages_for
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.views.server_details_view import DETAIL_FIELDS
from mcserver.presentation.views.status_text import STATUS_KEYS

SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)
CREATIVE = ServerConfiguration("creative", "creative-files", "fabric.jar", 2048)
MESSAGES = messages_for()


def window_for(qtbot: QtBot, repository: InMemoryRepository, root: Path, **options: object) -> MainWindow:
    window = MainWindow(services_for(repository, root=root, **options), MESSAGES)  # type: ignore[arg-type]
    qtbot.addWidget(window)
    return window


def item_texts(window: MainWindow) -> list[str]:
    widget = window.server_list_view.list_widget
    return [widget.item(index).text() for index in range(widget.count())]


def test_lists_servers_with_status_on_open(qtbot: QtBot, tmp_path: Path) -> None:
    window = window_for(qtbot, InMemoryRepository(SURVIVAL, CREATIVE), tmp_path)

    view = window.server_list_view
    assert view.pages.currentWidget() is view.list_widget
    assert view.server_ids() == ["survival", "creative"]
    stopped = MESSAGES.text("status.server.stopped")
    assert item_texts(window) == [
        MESSAGES.text("server_list.item", server_id="survival", status=stopped),
        MESSAGES.text("server_list.item", server_id="creative", status=stopped),
    ]
    assert window.server_details_view.pages.currentWidget() is window.server_details_view.empty_label


def test_selecting_an_item_shows_its_configuration(qtbot: QtBot, tmp_path: Path) -> None:
    window = window_for(qtbot, InMemoryRepository(SURVIVAL, CREATIVE), tmp_path)

    window.server_list_view.list_widget.setCurrentRow(1)

    details = window.server_details_view
    assert details.pages.currentWidget() is details.details_page
    assert details.title_label.text() == "creative"
    assert details.values["server_id"].text() == "creative"
    assert details.values["directory"].text() == "creative-files"
    assert details.values["location"].text() == str(tmp_path / "creative-files")
    assert details.values["jar_file"].text() == "fabric.jar"
    assert details.values["memory"].text() == MESSAGES.text("server_details.memory_value", memory_mb=2048)
    assert details.values["status"].text() == MESSAGES.text("status.server.stopped")
    assert window.server_list_view.list_widget.currentRow() == 1


def test_empty_collection_shows_empty_states(qtbot: QtBot, tmp_path: Path) -> None:
    window = window_for(qtbot, InMemoryRepository(), tmp_path)

    view = window.server_list_view
    assert view.pages.currentWidget() is view.empty_label
    assert view.empty_label.text() == MESSAGES.text("server_list.empty")
    assert window.server_details_view.empty_label.text() == MESSAGES.text("server_details.empty")


def test_refresh_action_and_button_reload_and_keep_selection(qtbot: QtBot, tmp_path: Path) -> None:
    repository = InMemoryRepository(SURVIVAL)
    window = window_for(qtbot, repository, tmp_path)
    window.server_list_view.list_widget.setCurrentRow(0)
    repository.items["creative"] = CREATIVE

    window.refresh_action.trigger()

    assert window.server_list_view.server_ids() == ["survival", "creative"]
    assert window.server_list_view.list_widget.currentRow() == 0
    assert window.server_details_view.title_label.text() == "survival"

    repository.items.pop("survival")
    qtbot.mouseClick(window.server_list_view.refresh_button, Qt.MouseButton.LeftButton)

    assert window.server_list_view.server_ids() == ["creative"]
    assert window.server_list_view.list_widget.currentRow() == -1
    assert window.server_details_view.pages.currentWidget() is window.server_details_view.empty_label


def test_storage_error_shows_message_instead_of_crashing(qtbot: QtBot, tmp_path: Path) -> None:
    repository = InMemoryRepository(SURVIVAL)
    repository.broken = True

    window = window_for(qtbot, repository, tmp_path)

    view = window.server_list_view
    assert view.pages.currentWidget() is view.error_label
    assert view.error_label.text() == MESSAGES.text("server_list.error.load")


def test_server_deleted_elsewhere_shows_details_message(qtbot: QtBot, tmp_path: Path) -> None:
    repository = InMemoryRepository(SURVIVAL, CREATIVE)
    window = window_for(qtbot, repository, tmp_path)
    repository.items.pop("creative")

    window.server_list_view.list_widget.setCurrentRow(1)

    details = window.server_details_view
    assert details.pages.currentWidget() is details.error_label
    assert details.error_label.text() == MESSAGES.text("server_details.error.gone")


def test_java_unavailable_mode_lists_servers_with_unknown_status(qtbot: QtBot, tmp_path: Path) -> None:
    window = window_for(qtbot, InMemoryRepository(SURVIVAL), tmp_path, java=False)
    window.server_list_view.list_widget.setCurrentRow(0)

    status = window.server_details_view.values["status"]
    assert status.text() == MESSAGES.text("status.server.unknown")
    assert status.toolTip() == MESSAGES.text("status.server.unknown_hint")
    assert window.java_status_label.text() == MESSAGES.text("status.java_missing")


def test_active_server_shows_running(qtbot: QtBot, tmp_path: Path) -> None:
    server_coordinator = coordinator()
    server_coordinator.start_server("survival")
    window = window_for(qtbot, InMemoryRepository(SURVIVAL), tmp_path, server_coordinator=server_coordinator)

    window.server_list_view.list_widget.setCurrentRow(0)

    assert window.server_details_view.values["status"].text() == MESSAGES.text("status.server.running")


def test_many_servers_fit_in_a_scrollable_list(qtbot: QtBot, tmp_path: Path) -> None:
    servers = [
        ServerConfiguration(f"server-{index:03}", f"server-{index:03}", "paper.jar", 1024) for index in range(300)
    ]
    window = window_for(qtbot, InMemoryRepository(*servers), tmp_path)
    window.show()

    assert window.server_list_view.list_widget.count() == 300
    assert window.server_list_view.list_widget.verticalScrollBar().maximum() > 0


def test_window_never_closes_backend_services(qtbot: QtBot, tmp_path: Path) -> None:
    closes: list[str] = []
    window = window_for(qtbot, InMemoryRepository(SURVIVAL), tmp_path, closes=closes)
    window.show()
    window.refresh_action.trigger()

    window.close()

    assert closes == []


def test_window_texts_come_from_catalog(qtbot: QtBot, tmp_path: Path) -> None:
    window = window_for(qtbot, InMemoryRepository(SURVIVAL), tmp_path)

    assert window.windowTitle() == MESSAGES.text("app.title")
    assert window.refresh_action.text() == MESSAGES.text("menu.file.refresh")
    assert window.server_list_view.refresh_button.text() == MESSAGES.text("server_list.refresh")


def test_all_dynamically_built_keys_exist_in_catalog() -> None:
    dynamic = {f"server_details.field.{field}" for field in DETAIL_FIELDS}
    dynamic |= set(STATUS_KEYS.values())

    assert set(STATUS_KEYS) == set(ServerStatus)
    assert sorted(dynamic - set(en.MESSAGES)) == []
