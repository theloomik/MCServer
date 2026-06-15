import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

import core
from services import PlayitDownloader
from styles import COLOR_ACCENT, COLOR_BG_CARD, COLOR_DANGER, COLOR_TEXT_SEC
from translations import _t
from widgets import ModernButton


class NetworkPage(QWidget):
    def __init__(self, manager, bridge, main):
        super().__init__()
        self.manager = manager
        self.bridge = bridge
        self.main = main
        self.current_server = None
        self.local_ip = "127.0.0.1"
        self.pub_ip = ""
        self.is_running = False

        self.playit_watchdog = QTimer(self)
        self.playit_watchdog.setInterval(1000)
        self.playit_watchdog.timeout.connect(self._sync_playit_state)
        self.bridge.playit_signal.connect(self.on_playit_data)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        h = QHBoxLayout()
        btn_back = ModernButton(_t("HOME_NAV_BACK"), bg_color="#27272a")
        btn_back.setFixedWidth(90)
        btn_back.clicked.connect(self.go_back)
        title = QLabel(_t("NETWORK_TITLE"))
        title.setStyleSheet("font-size: 24px; font-weight: 800; margin-left: 20px;")
        h.addWidget(btn_back)
        h.addWidget(title)
        h.addStretch()
        layout.addLayout(h)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)

        # IP card
        ip_card = QFrame()
        ip_card.setFixedSize(520, 430)
        ip_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        cl = QVBoxLayout(ip_card)
        cl.setContentsMargins(25, 25, 25, 25)
        cl.setSpacing(15)
        cl.addWidget(QLabel(_t("NETWORK_IP_CARD_TITLE"), styleSheet=f"color:{COLOR_TEXT_SEC}; font-weight: bold;"))
        self.lbl_local = QLabel(_t("NETWORK_LOCAL_DOTS"))
        self.lbl_local.setStyleSheet("font-size: 16px; padding: 5px;")
        self.lbl_local.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(self.lbl_local)
        self.lbl_pub = QLabel(_t("NETWORK_PUBLIC_OFF"))
        self.lbl_pub.setStyleSheet("font-size: 16px; color: #71717a; padding: 5px;")
        self.lbl_pub.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(self.lbl_pub)
        cl.addStretch()
        cards_row.addWidget(ip_card)

        # Playit card
        tun_card = QFrame()
        tun_card.setFixedSize(520, 430)
        tun_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        tl = QVBoxLayout(tun_card)
        tl.setContentsMargins(25, 25, 25, 25)
        tl.setSpacing(15)

        header_tun = QHBoxLayout()
        header_tun.addWidget(QLabel(_t("NETWORK_PLAYIT_TITLE"), styleSheet="font-size: 18px; font-weight: bold; color: white;"))
        self.btn_dl = QPushButton(_t("NETWORK_BTN_DOWNLOAD"))
        self.btn_dl.setCursor(Qt.PointingHandCursor)
        self.btn_dl.setStyleSheet(f"color: {COLOR_ACCENT}; border: none; font-weight: bold; text-align: right;")
        self.btn_dl.clicked.connect(self._start_download)
        header_tun.addWidget(self.btn_dl)
        tl.addLayout(header_tun)

        tl.addWidget(QLabel(_t("NETWORK_PLAYIT_DESC"), styleSheet=f"color:{COLOR_TEXT_SEC};"))

        path_row = QHBoxLayout()
        self.inp_playit_path = QLineEdit()
        self.inp_playit_path.setPlaceholderText(_t("NETWORK_PH_PLAYIT"))
        self.inp_playit_path.setReadOnly(True)
        self.inp_playit_path.setStyleSheet("background-color: #121214; border: 1px solid #3f3f46; border-radius: 8px; padding: 10px 12px;")
        btn_browse = ModernButton("📂", bg_color="#27272a")
        btn_browse.setFixedWidth(50)
        btn_browse.setStyleSheet(btn_browse.styleSheet() + "QPushButton { padding: 0px; font-size: 18px; }")
        btn_browse.clicked.connect(self._browse_playit)
        path_row.addWidget(self.inp_playit_path)
        path_row.addWidget(btn_browse)
        tl.addLayout(path_row)

        self.btn_run = ModernButton(_t("NETWORK_BTN_RUN"), bg_color=COLOR_ACCENT, text_color="black", is_accent=True)
        self.btn_run.clicked.connect(self._toggle_playit)
        tl.addWidget(self.btn_run)

        self.playit_log = QPlainTextEdit()
        self.playit_log.setPlaceholderText(_t("NETWORK_PH_LOGS"))
        self.playit_log.setStyleSheet("background-color: #0c0c0e; border: 1px solid #27272a; border-radius: 10px; font-family: Consolas; font-size: 11px;")
        self.playit_log.setFixedHeight(150)
        self.playit_log.setReadOnly(True)
        tl.addWidget(self.playit_log)

        cards_row.addWidget(tun_card)
        cards_row.addStretch()
        layout.addLayout(cards_row)
        layout.addStretch()

    def load(self, name):
        self.current_server = name
        self.local_ip = f"{core.ServerManager.get_local_ip()}:25565"
        self.lbl_local.setText(_t("NETWORK_LOCAL_LABEL", ip=self.local_ip))
        saved = self.manager.get_playit_path()
        if saved:
            self.inp_playit_path.setText(saved)
        self._update_ui_state()
        self.playit_watchdog.start()

    def _update_ui_state(self):
        if self.manager.playit_instance:
            self.is_running = True
            self.btn_run.setText(_t("NETWORK_BTN_STOP"))
            self.btn_run.setStyleSheet(
                f"background-color: {COLOR_DANGER}; color: white; border: none; "
                "border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;"
            )
            self.btn_run.set_glow_color(COLOR_DANGER)
            self.inp_playit_path.setEnabled(False)
        else:
            self.is_running = False
            self.btn_run.setText(_t("NETWORK_BTN_RUN"))
            self.btn_run.setStyleSheet(
                f"background-color: {COLOR_ACCENT}; color: black; border: none; "
                "border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;"
            )
            self.btn_run.set_glow_color(COLOR_ACCENT)
            self.inp_playit_path.setEnabled(True)
            self.lbl_pub.setText(_t("NETWORK_PUBLIC_OFF"))
            self.lbl_pub.setStyleSheet("font-size: 16px; color: #71717a; padding: 5px;")

    def _browse_playit(self):
        f, _ = QFileDialog.getOpenFileName(self, _t("NETWORK_DLG_FIND_PLAYIT"), "", "Executable (*.exe)")
        if f:
            self.inp_playit_path.setText(f)
            self.manager.set_playit_path(f)

    def _toggle_playit(self):
        if self.is_running:
            self.manager.toggle_playit(None)
            self._update_ui_state()
        else:
            path = self.inp_playit_path.text()
            if not path or not os.path.exists(path):
                self.main.show_toast(_t("NETWORK_MSG_BAD_PLAYIT_PATH"), True)
                return
            self.manager.set_playit_path(path)
            self.playit_log.clear()
            started = self.manager.toggle_playit(self.bridge.on_playit_output)
            if not started:
                self.main.show_toast(_t("NETWORK_MSG_PLAYIT_START_FAIL"), True)
            self._update_ui_state()

    def _start_download(self):
        dest, _ = QFileDialog.getSaveFileName(
            self, _t("NETWORK_DLG_SAVE_PLAYIT"), "playit.exe", "Executable (*.exe)"
        )
        if not dest:
            return
        self.btn_dl.setEnabled(False)
        self.playit_log.appendPlainText(_t("NETWORK_DL_CHECKING"))

        def _do():
            url, tag = PlayitDownloader.fetch_latest_windows_asset()
            self.playit_log.appendPlainText(_t("NETWORK_DL_PROGRESS", version=tag))
            sha = PlayitDownloader.download_to(url, Path(dest))
            return tag, sha, dest

        def _done(result):
            tag, sha, path = result
            self.playit_log.appendPlainText(_t("NETWORK_DL_OK", version=tag, sha=sha))
            self.inp_playit_path.setText(path)
            self.manager.set_playit_path(path)
            self.btn_dl.setEnabled(True)

        def _err(error):
            self.playit_log.appendPlainText(_t("NETWORK_DL_ERR", error=error))
            self.btn_dl.setEnabled(True)

        self.main.run_async(_do, _done, _err)

    @Slot(str, str)
    def on_playit_data(self, line, pub_ip):
        if line:
            self.playit_log.appendPlainText(line)
            self.playit_log.verticalScrollBar().setValue(self.playit_log.verticalScrollBar().maximum())
        if pub_ip and pub_ip != self.pub_ip:
            self.pub_ip = pub_ip
            self.lbl_pub.setText(_t("NETWORK_PUBLIC_LABEL", ip=pub_ip))
            self.lbl_pub.setStyleSheet(f"font-size: 16px; color: {COLOR_ACCENT}; font-weight: bold; padding: 5px;")

    def _sync_playit_state(self):
        running = bool(self.manager.playit_instance and self.manager.playit_instance.process)
        if self.is_running != running:
            self._update_ui_state()

    def go_back(self):
        self.playit_watchdog.stop()
        self.main.show_settings(self.current_server)
