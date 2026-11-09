"""Tests for the GUI composition root and main window shell (offscreen Qt)."""

from pathlib import Path

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSplitter
from pytestqt.qtbot import QtBot

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.bootstrap.server_runtime import build_server_creation, build_server_management
from mcserver.infrastructure.java_runtime import (
    JavaRuntime,
    JavaRuntimeNotFound,
    JavaRuntimeResolver,
    JavaRuntimeSource,
)
from mcserver.presentation.app import build_services, run
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.services import PresentationServices


class StubJavaResolver(JavaRuntimeResolver):
    def resolve(self) -> JavaRuntime:
        return JavaRuntime(Path("java"), JavaRuntimeSource.SYSTEM)


class MissingJavaResolver(JavaRuntimeResolver):
    def resolve(self) -> JavaRuntime:
        raise JavaRuntimeNotFound("No usable Java runtime was found.")


def fake_services(root: Path, *, java: bool, closes: list[str] | None = None) -> PresentationServices:
    """Services built from real (cheap, file-free until used) builders, with a recording closer."""
    calls = closes if closes is not None else []
    return PresentationServices(
        servers_root=root,
        management=build_server_management(root),
        server_creation=build_server_creation(root),
        coordinator=None if not java else ServerCoordinator(runner_factory=None),  # type: ignore[arg-type]
        output=ServerOutputBuffer() if java else None,
        java_problem=None if java else "No usable Java runtime was found.",
        closer=lambda: calls.append("closed"),
    )


# --- build_services ------------------------------------------------------------------


def test_full_mode_launches_from_configuration_store(tmp_path: Path) -> None:
    services = build_services(tmp_path, StubJavaResolver())
    try:
        assert services.can_run_servers
        assert services.java_problem is None
        assert isinstance(services.coordinator, ServerCoordinator)
        assert isinstance(services.output, ServerOutputBuffer)
        factory = services.coordinator._runner_factory  # type: ignore[attr-defined]
        assert type(factory._repository).__name__ == "StoredServerLaunchSettings"
    finally:
        services.close()


def test_degraded_mode_when_java_is_missing(tmp_path: Path) -> None:
    services = build_services(tmp_path, MissingJavaResolver())

    assert not services.can_run_servers
    assert services.coordinator is None and services.output is None
    assert services.java_problem == "No usable Java runtime was found."
    # Management and creation share one repository, as in the full runtime.
    shared = services.management._repository  # type: ignore[attr-defined]
    assert services.server_creation._management._repository is shared  # type: ignore[attr-defined]
    assert services.management.list_servers() == ()
    services.close()


def test_close_is_idempotent(tmp_path: Path) -> None:
    closes: list[str] = []
    services = fake_services(tmp_path, java=False, closes=closes)

    services.close()
    services.close()

    assert closes == ["closed"]
    assert services.closed


def test_full_mode_close_releases_runtime(tmp_path: Path) -> None:
    services = build_services(tmp_path, StubJavaResolver())
    assert services.output is not None
    services.output.subscribe(lambda _line: None)
    dispatcher = services.output._dispatcher  # type: ignore[attr-defined]

    services.close()

    assert dispatcher is not None and not dispatcher.is_alive()


# --- main window ------------------------------------------------------------------------


def test_window_shows_title_folder_and_java_status_from_catalog(qtbot: QtBot, tmp_path: Path) -> None:
    messages = messages_for()
    window = MainWindow(fake_services(tmp_path, java=True), messages)
    qtbot.addWidget(window)

    assert window.windowTitle() == messages.text("app.title")
    assert window.servers_folder_label.text() == messages.text("status.servers_folder", path=str(tmp_path))
    assert window.java_status_label.text() == messages.text("status.java_available")
    content = window.centralWidget()
    assert isinstance(content, QSplitter)
    assert content.widget(0) is window.server_list_view
    assert content.widget(1) is window.server_details_view


def test_window_explains_degraded_mode_with_details_on_hover(qtbot: QtBot, tmp_path: Path) -> None:
    messages = messages_for()
    window = MainWindow(fake_services(tmp_path, java=False), messages)
    qtbot.addWidget(window)

    assert window.java_status_label.text() == messages.text("status.java_missing")
    assert window.java_status_label.toolTip() == "No usable Java runtime was found."


def test_exit_action_closes_window(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(fake_services(tmp_path, java=True), messages_for())
    qtbot.addWidget(window)
    window.show()

    assert window.exit_action.text() == messages_for().text("menu.file.exit")
    window.exit_action.trigger()

    assert not window.isVisible()


def test_window_does_not_close_services(qtbot: QtBot, tmp_path: Path) -> None:
    closes: list[str] = []
    window = MainWindow(fake_services(tmp_path, java=True, closes=closes), messages_for())
    qtbot.addWidget(window)
    window.show()

    window.close()

    assert closes == []


# --- run (event loop lifetime) ------------------------------------------------------------


def test_run_closes_services_exactly_once_after_event_loop(qapp: QApplication, tmp_path: Path) -> None:
    closes: list[str] = []
    services = fake_services(tmp_path, java=True, closes=closes)
    QTimer.singleShot(0, qapp.quit)

    exit_code = run(qapp, services, messages_for())

    assert exit_code == 0
    assert closes == ["closed"]


def test_run_closes_services_even_if_window_creation_fails(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closes: list[str] = []
    services = fake_services(tmp_path, java=False, closes=closes)

    def broken_window(*_args: object) -> None:
        raise RuntimeError("widget construction failed")

    monkeypatch.setattr("mcserver.presentation.app.MainWindow", broken_window)

    with pytest.raises(RuntimeError, match="widget construction failed"):
        run(qapp, services, messages_for())
    assert closes == ["closed"]
