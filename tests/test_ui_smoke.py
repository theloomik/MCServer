import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import ui


def test_main_window_can_be_created(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    app = QApplication.instance() or QApplication([])
    window = ui.MainWindow()

    assert window.windowTitle()

    window.close()
    app.processEvents()
