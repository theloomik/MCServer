"""MCServer's own log file: written next to the servers folder, rotated, never fatal."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot
from test_m2_gui import SURVIVAL
from test_m2_gui import Setup as M2Setup

from mcserver.presentation import log_file


@pytest.fixture
def root_logger() -> Iterator[logging.Logger]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield root
    for handler in root.handlers:
        if handler not in handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level)


def test_the_logs_folder_sits_next_to_the_servers_folder(tmp_path: Path) -> None:
    assert log_file.logs_folder(tmp_path / "MCServer" / "servers") == tmp_path / "MCServer" / "logs"


def test_warnings_and_errors_reach_the_file(root_logger: logging.Logger, tmp_path: Path) -> None:
    path = log_file.start_log_file(tmp_path / "logs", "9.9.9")
    assert path == tmp_path / "logs" / "mcserver.log"
    logging.getLogger("mcserver.test").error("Something broke", exc_info=ValueError("bad value"))
    for handler in root_logger.handlers:
        handler.flush()
    text = path.read_text(encoding="utf-8")
    assert "MCServer 9.9.9 starting" in text
    assert "ERROR" in text and "Something broke" in text and "ValueError: bad value" in text


def test_the_file_is_rotated_and_added_once(root_logger: logging.Logger, tmp_path: Path) -> None:
    log_file.start_log_file(tmp_path, "1")
    log_file.start_log_file(tmp_path, "1")
    handlers = [handler for handler in root_logger.handlers if isinstance(handler, RotatingFileHandler)]
    mine = [handler for handler in handlers if Path(handler.baseFilename) == (tmp_path / "mcserver.log").resolve()]
    assert len(mine) == 1
    assert (mine[0].maxBytes, mine[0].backupCount) == (log_file.MAX_BYTES, log_file.BACKUP_COUNT)


def test_a_folder_that_cannot_be_created_leaves_mcserver_running(root_logger: logging.Logger, tmp_path: Path) -> None:
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("a file where the folder should be")
    assert log_file.start_log_file(blocker / "logs", "1") is None


def test_settings_open_the_logs_folder(qtbot: QtBot, tmp_path: Path) -> None:
    root = tmp_path / "servers"
    root.mkdir()
    (tmp_path / "logs").mkdir()
    opened: list[Path] = []
    setup = M2Setup(qtbot, root, SURVIVAL)
    window = setup.window
    window._open_folder = lambda path: opened.append(path) or True  # type: ignore[method-assign]
    window.open_settings_dialog()
    assert window.settings_dialog is not None
    window.settings_dialog.logs_button.click()
    assert opened == [tmp_path / "logs"]
