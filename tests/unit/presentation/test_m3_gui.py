"""Offscreen Qt tests for M3: properties tab, backups tab, resource tiles and the unclean-shutdown shortcut."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import FakeRunnerFactory, InMemoryRepository, MemoryFilesystem, creation_for
from PySide6.QtWidgets import QCheckBox, QComboBox, QLineEdit, QSpinBox
from pytestqt.qtbot import QtBot

from mcserver.application.backup_schedule import BackupSchedule, ScheduledBackupResult, ScheduledBackups
from mcserver.application.backups import BackupInfo, BackupKind, BackupService
from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_metrics import ServerMetricsSnapshot
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.application.server_properties import ServerPropertiesService
from mcserver.application.worlds import WorldService
from mcserver.domain.lifecycle import ServerState
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.infrastructure.recycle_bin import RecycleBinServerFilesRemover
from mcserver.infrastructure.server_properties_file import FileServerPropertiesStore
from mcserver.infrastructure.world_folders import LocalWorldStore
from mcserver.infrastructure.zip_backup_store import ZipBackupStore
from mcserver.presentation.controllers.properties import PropertiesController
from mcserver.presentation.i18n import messages_for
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.services import PresentationServices
from mcserver.presentation.views.backups_view import format_created_at
from tests.runtime_fakes import ManualScheduler

MESSAGES = messages_for()
SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 2048)
CREATIVE = ServerConfiguration("creative", "creative", "paper.jar", 1024)


def no_recycle_bin(_path: Path) -> None:
    raise OSError("tests never touch the real Recycle Bin")


class Metrics:
    def __init__(self) -> None:
        self.snapshot: ServerMetricsSnapshot | None = None

    def sample(self) -> ServerMetricsSnapshot | None:
        return self.snapshot


class Setup:
    def __init__(self, qtbot: QtBot, root: Path, *, with_m3: bool = True, restore_answer: bool = True) -> None:
        self.root = root
        for configuration in (SURVIVAL, CREATIVE):
            world = root / configuration.directory / "world"
            world.mkdir(parents=True)
            (world / "level.dat").write_bytes(b"level v1")
        (root / "survival" / "server.properties").write_text(
            "#Minecraft server properties\nmotd=Hello\npvp=true\ndifficulty=easy\nmax-players=20\n"
            "view-distance=lots\ncustom-key=abc\n",
            encoding="latin-1",
        )
        self.repository = InMemoryRepository(SURVIVAL, CREATIVE)
        self.coordinator = ServerCoordinator(FakeRunnerFactory(), scheduler=ManualScheduler())
        management = ServerManagement(
            self.repository, _NoLegacy(), active_server=lambda: self.coordinator.active_server_id
        )
        self.metrics = Metrics()
        store = ZipBackupStore(root, RecycleBinServerFilesRemover(root, no_recycle_bin))
        self.backups = BackupService(self.repository, self.coordinator, store)
        self.scheduled = ScheduledBackups(store, self.backups, self.coordinator)
        services = PresentationServices(
            servers_root=root,
            management=management,
            server_creation=creation_for(self.repository, MemoryFilesystem()),
            coordinator=self.coordinator,
            output=ServerOutputBuffer(),
            java_problem=None,
            closer=lambda: None,
            properties=ServerPropertiesService(
                FileServerPropertiesStore(root, self.repository), lambda: self.coordinator.active_server_id
            )
            if with_m3
            else None,
            metrics=self.metrics if with_m3 else None,  # type: ignore[arg-type]
            backups=self.backups if with_m3 else None,
            scheduled_backups=self.scheduled if with_m3 else None,
            worlds=WorldService(
                self.repository,
                LocalWorldStore(root, RecycleBinServerFilesRemover(root, no_recycle_bin)),
                ServerPropertiesService(FileServerPropertiesStore(root, self.repository)),
                lambda: self.coordinator.active_server_id,
            )
            if with_m3
            else None,
        )
        self.world_answers = WorldAnswers()
        self.restore_questions: list[str] = []
        self.delete_questions: list[str] = []

        def confirm_restore(backup: BackupInfo) -> bool:
            self.restore_questions.append(backup.backup_id)
            return restore_answer

        def confirm_delete(backup: BackupInfo) -> bool:
            self.delete_questions.append(backup.backup_id)
            return True

        self.window = MainWindow(
            services,
            MESSAGES,
            confirm_exit=lambda _server_id: True,
            notify_unclean=lambda _incident: None,
            confirm_restore=confirm_restore,
            confirm_delete_backup=confirm_delete,
            world_dialogs=self.world_answers,
        )
        qtbot.addWidget(self.window)
        self.window.show()
        self.qtbot = qtbot

    def select(self, server_id: str) -> None:
        self.window.server_list_controller.select(server_id)

    def wait_for_backups(self) -> None:
        self.qtbot.waitUntil(lambda: not self.window.backups_controller.busy, timeout=10000)


class WorldAnswers:
    def __init__(self) -> None:
        self.new: tuple[str, str] | None = None
        self.source: str | None = None
        self.name: str | None = None
        self.suggested: list[str] = []
        self.export: str | None = None
        self.delete = True

    def new_world(self) -> tuple[str, str] | None:
        return self.new

    def import_source(self, zip_file: bool) -> str | None:
        return self.source

    def world_name(self, suggested: str) -> str | None:
        self.suggested.append(suggested)
        return self.name or suggested

    def export_path(self, name: str) -> str | None:
        return self.export

    def confirm_delete(self, name: str) -> bool:
        return self.delete


class _NoLegacy:
    def list_server_ids(self) -> tuple[str, ...]:
        return ()

    def read_server(self, server_id: str) -> ServerConfiguration:
        raise AssertionError("not used")


# --- tabs ------------------------------------------------------------------------------------------


def test_dashboard_has_properties_and_backups_tabs(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    tabs = setup.window.dashboard_view.tabs
    assert [tabs.tabText(index) for index in range(tabs.count())] == ["Overview", "Properties", "Worlds", "Backups"]
    assert not setup.window.dashboard_view.metrics_card.isHidden()


def test_without_m3_services_only_the_overview_tab_is_shown(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, with_m3=False)
    assert setup.window.dashboard_view.tabs.count() == 1
    assert setup.window.properties_view is None and setup.window.backups_view is None
    assert setup.window.dashboard_view.metrics_card.isHidden()


# --- properties (M3-GUI-02) -----------------------------------------------------------------------


def test_properties_use_typed_editors_and_keep_unreadable_values_as_text(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None
    editors = view.editors
    assert isinstance(editors["pvp"], QCheckBox) and editors["pvp"].isChecked()
    assert isinstance(editors["difficulty"], QComboBox) and editors["difficulty"].currentText() == "easy"
    assert isinstance(editors["max-players"], QSpinBox) and editors["max-players"].value() == 20
    assert isinstance(editors["view-distance"], QLineEdit)  # "lots" cannot be shown by a number field
    assert isinstance(editors["custom-key"], QLineEdit) and editors["custom-key"].text() == "abc"
    assert not view.message.isVisibleTo(view)


def test_saving_properties_writes_only_changed_values(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None
    before = (tmp_path / "survival" / "server.properties").read_text(encoding="latin-1")
    view.editors["motd"].setText("Привіт")  # type: ignore[union-attr]
    view.editors["max-players"].setValue(8)  # type: ignore[union-attr]
    view.save_button.click()

    text = (tmp_path / "survival" / "server.properties").read_text(encoding="latin-1")
    assert "motd=\\u041f\\u0440\\u0438\\u0432\\u0456\\u0442" in text
    assert "max-players=8" in text
    assert "view-distance=lots" in text and "#Minecraft server properties" in text  # untouched lines stay
    assert text.count("\n") == before.count("\n")
    assert view.message.text() == MESSAGES.text("properties.saved")


def test_invalid_property_is_marked_and_nothing_is_saved(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None
    path = tmp_path / "survival" / "server.properties"
    before = path.read_bytes()
    view.editors["view-distance"].setText("far")  # type: ignore[union-attr]
    view.editors["motd"].setText("Changed")  # type: ignore[union-attr]
    view.save_button.click()

    assert path.read_bytes() == before
    assert view.message.text() == MESSAGES.text("properties.invalid")
    assert "view-distance" in setup.window.properties_controller.state.problems


def test_missing_properties_file_shows_a_note_and_saves_only_what_was_typed(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("creative")
    view = setup.window.properties_view
    assert view is not None
    assert view.message.text() == MESSAGES.text("properties.missing")
    assert all(isinstance(editor, QLineEdit) and editor.text() == "" for editor in view.editors.values())
    view.editors["motd"].setText("Creative")  # type: ignore[union-attr]
    view.save_button.click()

    assert (tmp_path / "creative" / "server.properties").read_text(encoding="latin-1").splitlines()[1:] == [
        "motd=Creative"
    ]


def test_filter_hides_non_matching_properties(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.properties_view
    assert view is not None
    view.filter_edit.setText("motd")
    assert view.editors["motd"].isVisibleTo(view)
    assert not view.editors["pvp"].isVisibleTo(view)


class _RunningService:
    def __init__(self) -> None:
        self.saved: list[dict[str, str]] = []

    def load(self, server_id: str):  # type: ignore[no-untyped-def]
        from mcserver.application.server_properties import ServerPropertiesView

        return ServerPropertiesView(server_id, {"motd": "a"}, True, True)

    def save(self, server_id: str, changes: dict[str, str]) -> bool:
        self.saved.append(changes)
        return True


def test_saving_while_running_says_a_restart_is_needed(qtbot: QtBot) -> None:
    service = _RunningService()
    controller = PropertiesController(service)  # type: ignore[arg-type]
    controller.show_server("survival")
    assert controller.save({"motd": "b"}) is True
    assert service.saved == [{"motd": "b"}]
    message = controller.state.message
    assert message is not None and message.key == "properties.saved_restart"


# --- backups (M3-GUI-04) --------------------------------------------------------------------------


def test_backup_create_restore_and_delete_from_the_tab(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.backups_view
    assert view is not None
    assert view.empty_label.isVisibleTo(view) and not view.table.isVisibleTo(view)

    view.note_edit.setText("before the update")
    view.create_button.click()
    setup.wait_for_backups()
    assert view.table.rowCount() == 1
    assert view.table.item(0, 3).text() == "before the update"
    assert view.message.text().startswith("Backup ")

    (tmp_path / "survival" / "world" / "level.dat").write_bytes(b"damaged")
    view.table.selectRow(0)
    assert view.restore_button.isEnabled()
    view.restore_button.click()
    setup.wait_for_backups()
    assert setup.restore_questions and (tmp_path / "survival" / "world" / "level.dat").read_bytes() == b"level v1"
    kinds = [backup.kind for backup in setup.window.backups_controller.state.backups]
    assert sorted(kinds) == [BackupKind.MANUAL, BackupKind.SAFETY]

    rows_before = view.table.rowCount()
    view.table.selectRow(0)
    view.delete_button.click()
    setup.wait_for_backups()
    assert setup.delete_questions and view.table.rowCount() == rows_before - 1
    assert (tmp_path / ".trash").is_dir()  # moved, never deleted


def test_declined_restore_changes_nothing(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path, restore_answer=False)
    setup.select("survival")
    view = setup.window.backups_view
    assert view is not None
    view.create_button.click()
    setup.wait_for_backups()
    (tmp_path / "survival" / "world" / "level.dat").write_bytes(b"newer")
    view.table.selectRow(0)
    view.restore_button.click()
    assert setup.restore_questions
    assert not setup.window.backups_controller.busy
    assert (tmp_path / "survival" / "world" / "level.dat").read_bytes() == b"newer"


def test_restore_is_disabled_while_the_server_is_active(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.backups_view
    assert view is not None
    view.create_button.click()
    setup.wait_for_backups()
    view.table.selectRow(0)
    setup.window.backups_controller.set_active_server("survival")
    assert not view.restore_button.isEnabled()
    assert view.restore_hint.isVisibleTo(view)
    setup.window.backups_controller.set_active_server(None)
    assert view.restore_button.isEnabled()


def test_open_backups_selects_the_server_and_shows_the_tab(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("creative")
    setup.window.open_backups("survival")
    assert setup.window.dashboard_controller.state.row is not None
    assert setup.window.dashboard_controller.state.row.server_id == "survival"
    assert setup.window.dashboard_view.current_tab == "backups"


@pytest.mark.parametrize(
    ("value", "expected_prefix"),
    [("2026-11-23T10:15:00", "2026-11-23 10:15"), ("not a date", "not a date")],
)
def test_created_at_formatting(value: str, expected_prefix: str) -> None:
    assert format_created_at(value) == expected_prefix


# --- resource tiles (M3-GUI-03) -------------------------------------------------------------------


def test_resource_tiles_show_the_selected_running_server_only(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    values = setup.window.dashboard_view.metric_values
    assert values["cpu"].text() == MESSAGES.text("metrics.idle")

    setup.metrics.snapshot = ServerMetricsSnapshot("survival", ServerState.RUNNING, 12.4, 1536.2, 2048, 3725)
    setup.window.sample_metrics()
    assert values["cpu"].text() == "12 %"
    assert values["memory"].text() == MESSAGES.text("metrics.memory_gb", used="1.5")
    assert setup.window.dashboard_view.tiles["memory"].detail.text() == MESSAGES.text(
        "metrics.memory_of", allocated="2"
    )
    assert values["uptime"].text() == "1:02:05"

    setup.select("creative")
    assert values["cpu"].text() == MESSAGES.text("metrics.idle")


# --- scheduled backups (ADR 0008) ------------------------------------------------------------------


def test_schedule_controls_store_the_schedule(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    view = setup.window.backups_view
    assert view is not None
    assert view.schedule_host.isVisibleTo(view) and not view.schedule_check.isChecked()
    assert not view.interval_spin.isEnabled()

    view.schedule_check.setChecked(True)
    assert setup.scheduled.schedule("survival") == BackupSchedule(enabled=True)
    assert view.interval_spin.isEnabled()
    view.interval_spin.setValue(12)
    view.keep_spin.setValue(3)
    assert setup.scheduled.schedule("survival") == BackupSchedule(True, 12, 3)
    assert view.message.text() == MESSAGES.text("backups.schedule.saved")

    setup.select("creative")
    assert not view.schedule_check.isChecked()
    setup.select("survival")
    assert view.schedule_check.isChecked() and view.interval_spin.value() == 12


def test_nothing_runs_on_schedule_while_the_server_is_stopped(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.scheduled.set_schedule("survival", BackupSchedule(enabled=True, interval_hours=1, keep=2))
    assert setup.window.backups_controller.run_scheduled() is False


class _DueSchedules:
    def __init__(self, result: ScheduledBackupResult) -> None:
        self.result = result

    def schedule(self, server_id: str) -> BackupSchedule:
        return BackupSchedule()

    def due_server(self) -> str | None:
        return "survival"

    def run_due(self, progress=None, cancel=None):  # type: ignore[no-untyped-def]
        return self.result


def test_scheduled_run_reports_in_the_notifications(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    setup.select("survival")
    controller = setup.window.backups_controller
    backup = BackupInfo("20261123-120000-scheduled", "survival", "2026-11-23T12:00:00+00:00", 10, BackupKind.SCHEDULED)
    controller._schedules = _DueSchedules(ScheduledBackupResult(backup, ("old",)))  # type: ignore[attr-defined]
    assert controller.run_scheduled() is True
    qtbot.waitUntil(lambda: not controller.busy)
    expected = MESSAGES.text("backups.scheduled_created", server_id="survival", backup_id=backup.backup_id, removed=1)
    assert expected in setup.window.notification_texts()


# --- worlds (M3-GUI-07) ---------------------------------------------------------------------------


def worlds_of(setup: Setup) -> list[str]:
    return [world.name for world in setup.window.worlds_controller.state.worlds]


def wait_for_worlds(setup: Setup) -> None:
    controller = setup.window.worlds_controller
    setup.qtbot.waitUntil(lambda: not controller.busy and not controller.state.loading, timeout=10000)


def select_world(setup: Setup, name: str) -> None:
    view = setup.window.worlds_view
    assert view is not None
    view.table.selectRow(worlds_of(setup).index(name))


def test_worlds_tab_lists_switches_and_creates(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    (tmp_path / "survival" / "lobby").mkdir()
    (tmp_path / "survival" / "lobby" / "level.dat").write_bytes(b"lobby")
    setup.select("survival")
    wait_for_worlds(setup)
    view = setup.window.worlds_view
    assert view is not None
    assert worlds_of(setup) == ["world", "lobby"]
    assert view.table.item(0, 0).text() == MESSAGES.text("worlds.active_name", name="world")
    assert view.current_label.text() == MESSAGES.text("worlds.current", name="world")

    select_world(setup, "world")
    assert not view.use_button.isEnabled() and not view.delete_button.isEnabled()  # the current world
    select_world(setup, "lobby")
    assert view.use_button.isEnabled()
    view.use_button.click()
    wait_for_worlds(setup)
    assert "level-name=lobby" in (tmp_path / "survival" / "server.properties").read_text(encoding="latin-1")
    assert worlds_of(setup)[0] == "lobby"
    assert setup.window.properties_controller.state.values.get("level-name") == "lobby"  # Properties tab follows

    setup.world_answers.new = ("fresh", "42")
    view.new_button.click()
    wait_for_worlds(setup)
    assert view.current_label.text() == MESSAGES.text("worlds.current_new", name="fresh")


def test_worlds_import_export_and_delete(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    source = tmp_path / "downloads" / "Skyblock"
    source.mkdir(parents=True)
    (source / "level.dat").write_bytes(b"sky")
    setup.select("survival")
    wait_for_worlds(setup)
    view = setup.window.worlds_view
    assert view is not None

    setup.world_answers.source = str(source)
    view.import_folder_button.click()
    wait_for_worlds(setup)
    assert setup.world_answers.suggested == ["Skyblock"]
    assert "Skyblock" in worlds_of(setup)

    select_world(setup, "Skyblock")
    setup.world_answers.export = str(tmp_path / "sky.zip")
    view.export_button.click()
    wait_for_worlds(setup)
    assert (tmp_path / "sky.zip").is_file()

    select_world(setup, "Skyblock")
    view.delete_button.click()
    wait_for_worlds(setup)
    assert "Skyblock" not in worlds_of(setup)
    assert (tmp_path / ".trash").is_dir()


def test_switching_worlds_is_disabled_while_the_server_runs(qtbot: QtBot, tmp_path: Path) -> None:
    setup = Setup(qtbot, tmp_path)
    (tmp_path / "survival" / "lobby").mkdir()
    (tmp_path / "survival" / "lobby" / "level.dat").write_bytes(b"lobby")
    setup.select("survival")
    wait_for_worlds(setup)
    view = setup.window.worlds_view
    assert view is not None
    setup.window.worlds_controller.set_active_server("survival")
    select_world(setup, "lobby")
    assert not view.use_button.isEnabled() and not view.new_button.isEnabled()
    assert view.running_hint.isVisibleTo(view)
    assert view.delete_button.isEnabled()  # other worlds can still be managed
    select_world(setup, "world")
    assert not view.export_button.isEnabled()  # the running world: use a backup instead
