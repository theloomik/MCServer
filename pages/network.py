from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QProgressBar, QSizePolicy, QVBoxLayout, QWidget,
)

import core
from services import PlayitDownloader
from styles import (
    COLOR_ACCENT, COLOR_BG_CARD, COLOR_BORDER, COLOR_DANGER,
    COLOR_TEXT_MAIN, COLOR_TEXT_SEC, copy_to_clipboard,
)
from translations import _t
from widgets import ModernButton


def _divider(color=None):
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {color or COLOR_BORDER}; border: none;")
    return line


def _ip_row_frame(label_text: str):
    """Returns (outer_frame, ip_label, copy_btn)."""
    frame = QFrame()
    frame.setStyleSheet(
        f"background-color: #121214; border-radius: 10px; border: 1px solid {COLOR_BORDER};"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    layout.setSpacing(6)

    type_lbl = QLabel(label_text)
    type_lbl.setStyleSheet(
        f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 600;"
        " background: transparent; border: none;"
    )
    layout.addWidget(type_lbl)

    ip_row = QHBoxLayout()
    ip_row.setSpacing(8)
    ip_lbl = QLabel("...")
    ip_lbl.setStyleSheet(
        "font-size: 17px; font-weight: 700; color: white;"
        " background: transparent; border: none;"
    )
    ip_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    ip_row.addWidget(ip_lbl, 1)

    copy_btn = ModernButton("📋", bg_color="#27272a")
    copy_btn.setFixedSize(36, 36)
    copy_btn.setToolTip("Копіювати")
    ip_row.addWidget(copy_btn)
    layout.addLayout(ip_row)
    return frame, ip_lbl, copy_btn


class NetworkPage(QWidget):
    def __init__(self, manager, bridge, main):
        super().__init__()
        self.manager = manager
        self.bridge = bridge
        self.main = main
        self.current_server = None
        self.local_ip = ""
        self.pub_ip = ""
        self.is_running = False
        self._server_port = 25565

        self.tunnel_watchdog = QTimer(self)
        self.tunnel_watchdog.setInterval(1000)
        self.tunnel_watchdog.timeout.connect(self._sync_tunnel_state)
        self.bridge.tunnel_signal.connect(self.on_tunnel_data)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)

        # ── Header ───────────────────────────────────────────────────────────
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
        layout.addSpacing(20)
        layout.addWidget(_divider())
        layout.addSpacing(20)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)

        # ── IP card ──────────────────────────────────────────────────────────
        ip_card = QFrame()
        ip_card.setFixedWidth(520)
        ip_card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        ip_card.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; border-radius: 16px;"
            f" border: 1px solid {COLOR_BORDER};"
        )
        cl = QVBoxLayout(ip_card)
        cl.setContentsMargins(24, 24, 24, 24)
        cl.setSpacing(14)

        ip_hdr = QHBoxLayout()
        ip_icon = QLabel("🔌")
        ip_icon.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        ip_hdr.addWidget(ip_icon)
        ip_title = QLabel(_t("NETWORK_IP_CARD_TITLE"))
        ip_title.setStyleSheet(
            f"color: {COLOR_TEXT_MAIN}; font-size: 15px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        ip_hdr.addWidget(ip_title)
        ip_hdr.addStretch()
        cl.addLayout(ip_hdr)
        cl.addWidget(_divider())

        local_frame, self.lbl_local, btn_copy_local = _ip_row_frame(
            _t("NETWORK_LOCAL_ADDR_LABEL")
        )
        btn_copy_local.clicked.connect(lambda: self._copy_ip(self.local_ip))
        cl.addWidget(local_frame)

        pub_frame, self.lbl_pub, self.btn_copy_pub = _ip_row_frame(
            _t("NETWORK_PUBLIC_ADDR_LABEL")
        )
        self.lbl_pub.setStyleSheet(
            "font-size: 14px; color: #71717a; background: transparent; border: none;"
        )
        self.btn_copy_pub.setEnabled(False)
        self.btn_copy_pub.clicked.connect(lambda: self._copy_ip(self.pub_ip))
        cl.addWidget(pub_frame)

        # Tunnel status badge
        self.tunnel_status_frame = QFrame()
        self.tunnel_status_frame.setStyleSheet(
            "background-color: #1c1c1f; border-radius: 8px; border: 1px solid #27272a;"
        )
        ts_row = QHBoxLayout(self.tunnel_status_frame)
        ts_row.setContentsMargins(14, 10, 14, 10)
        self.tunnel_status_lbl = QLabel(_t("BORE_STATUS_INACTIVE"))
        self.tunnel_status_lbl.setStyleSheet(
            "color: #71717a; font-size: 12px; font-weight: 600;"
            " background: transparent; border: none;"
        )
        ts_row.addWidget(self.tunnel_status_lbl)
        ts_row.addStretch()
        cl.addWidget(self.tunnel_status_frame)
        cl.addStretch()
        cards_row.addWidget(ip_card)

        # ── Playit card ───────────────────────────────────────────────────────
        playit_card = QFrame()
        playit_card.setFixedWidth(520)
        playit_card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        playit_card.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; border-radius: 16px;"
            f" border: 1px solid {COLOR_BORDER};"
        )
        tl = QVBoxLayout(playit_card)
        tl.setContentsMargins(24, 24, 24, 24)
        tl.setSpacing(14)

        playit_hdr = QHBoxLayout()
        playit_icon = QLabel("🎮")
        playit_icon.setStyleSheet("font-size: 16px; background: transparent; border: none;")
        playit_hdr.addWidget(playit_icon)
        playit_title = QLabel(_t("BORE_TITLE"))
        playit_title.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: white;"
            " background: transparent; border: none;"
        )
        playit_hdr.addWidget(playit_title)
        playit_hdr.addStretch()
        tl.addLayout(playit_hdr)
        tl.addWidget(_divider())

        playit_desc = QLabel(_t("BORE_DESC"))
        playit_desc.setWordWrap(True)
        playit_desc.setStyleSheet(
            f"color: {COLOR_TEXT_SEC}; font-size: 12px; background: transparent; border: none;"
        )
        tl.addWidget(playit_desc)

        # Download progress (hidden by default)
        self.progress_frame = QFrame()
        self.progress_frame.setStyleSheet("background: transparent; border: none;")
        prog_l = QVBoxLayout(self.progress_frame)
        prog_l.setContentsMargins(0, 0, 0, 0)
        prog_l.setSpacing(4)
        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_SEC}; font-size: 11px; background: transparent; border: none;"
        )
        prog_l.addWidget(self.progress_lbl)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(
            f"QProgressBar {{ background-color: #27272a; border-radius: 3px; border: none; }}"
            f"QProgressBar::chunk {{ background-color: {COLOR_ACCENT}; border-radius: 3px; }}"
        )
        self.progress_bar.setRange(0, 100)
        prog_l.addWidget(self.progress_bar)
        self.progress_frame.hide()
        tl.addWidget(self.progress_frame)

        # Start / Stop button
        self.btn_run = ModernButton(
            _t("BORE_BTN_START"), bg_color=COLOR_ACCENT, text_color="black", is_accent=True
        )
        self.btn_run.setFixedHeight(52)
        self.btn_run.clicked.connect(self._on_btn_run)
        tl.addWidget(self.btn_run)

        # Collapsible log area with label
        log_lbl = QLabel(_t("BORE_LOGS_LABEL"))
        log_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 600;"
            " background: transparent; border: none;"
        )
        tl.addWidget(log_lbl)
        self.tunnel_log = QPlainTextEdit()
        self.tunnel_log.setPlaceholderText(_t("BORE_PH_LOGS"))
        self.tunnel_log.setStyleSheet(
            "QPlainTextEdit {"
            "  background-color: #0c0c0e;"
            "  border: 1px solid #27272a;"
            "  border-radius: 10px;"
            "  font-family: Consolas, monospace;"
            "  font-size: 10px;"
            "  color: #a1a1aa;"
            "  padding: 8px;"
            "}"
        )
        self.tunnel_log.setMinimumHeight(100)
        self.tunnel_log.setMaximumHeight(160)
        self.tunnel_log.setReadOnly(True)
        tl.addWidget(self.tunnel_log)

        cards_row.addWidget(playit_card)
        cards_row.addStretch()
        layout.addLayout(cards_row)
        layout.addStretch()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _copy_ip(self, ip: str):
        if ip:
            copy_to_clipboard(ip)
            self.main.show_toast(_t("NETWORK_MSG_IP_COPIED"), False)

    def _set_progress(self, done: int, total: int):
        if total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(done / total * 100))
            self.progress_lbl.setText(
                _t("BORE_DL_PROGRESS",
                   done=f"{done / 1_048_576:.1f}",
                   total=f"{total / 1_048_576:.1f}")
            )
        else:
            self.progress_bar.setRange(0, 0)

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def _read_server_port(self, name: str) -> int:
        try:
            server_dir = self.manager.path_policy.directory_for_name(name)
            props_path = server_dir / "server.properties"
            if props_path.is_file():
                for line in props_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("server-port="):
                        return int(line.split("=", 1)[1].strip())
        except (ValueError, OSError):
            pass
        return 25565

    def load(self, name):
        self.current_server = name
        self._server_port = self._read_server_port(name)
        self.local_ip = f"{core.ServerManager.get_local_ip()}:{self._server_port}"
        self.lbl_local.setText(self.local_ip)
        self._update_ui_state()
        self.tunnel_watchdog.start()

    def _update_ui_state(self):
        running = bool(self.manager.tunnel_instance and self.manager.tunnel_instance.process)
        self.is_running = running
        self.progress_frame.hide()

        if running:
            self.btn_run.setText(_t("BORE_BTN_STOP"))
            self.btn_run.setStyleSheet(
                f"background-color: {COLOR_DANGER}; color: white; border: none;"
                " border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;"
            )
            self.btn_run.set_glow_color(COLOR_DANGER)
            self.btn_run.setEnabled(True)
            self.tunnel_status_lbl.setText(_t("BORE_STATUS_ACTIVE"))
            self.tunnel_status_lbl.setStyleSheet(
                f"color: {COLOR_ACCENT}; font-size: 12px; font-weight: 600;"
                " background: transparent; border: none;"
            )
            self.tunnel_status_frame.setStyleSheet(
                f"background-color: rgba(16,185,129,0.08); border-radius: 8px;"
                f" border: 1px solid rgba(16,185,129,0.35);"
            )
        else:
            self.pub_ip = ""
            self.lbl_pub.setText(_t("NETWORK_PUBLIC_OFF"))
            self.lbl_pub.setStyleSheet(
                "font-size: 14px; color: #71717a; background: transparent; border: none;"
            )
            self.btn_copy_pub.setEnabled(False)
            self.btn_run.setText(_t("BORE_BTN_START"))
            self.btn_run.setStyleSheet(
                f"background-color: {COLOR_ACCENT}; color: black; border: none;"
                " border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;"
            )
            self.btn_run.set_glow_color(COLOR_ACCENT)
            self.btn_run.setEnabled(True)
            self.tunnel_status_lbl.setText(_t("BORE_STATUS_INACTIVE"))
            self.tunnel_status_lbl.setStyleSheet(
                "color: #71717a; font-size: 12px; font-weight: 600;"
                " background: transparent; border: none;"
            )
            self.tunnel_status_frame.setStyleSheet(
                "background-color: #1c1c1f; border-radius: 8px; border: 1px solid #27272a;"
            )

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_btn_run(self):
        if self.is_running:
            self.manager.toggle_tunnel(self._server_port, self.bridge.on_tunnel_output)
            self._update_ui_state()
            return

        self.btn_run.setEnabled(False)
        if PlayitDownloader.is_downloaded():
            self._start_tunnel()
        else:
            self._download_then_start()

    def _download_then_start(self):
        self.progress_frame.show()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_lbl.setText(_t("BORE_STATUS_DOWNLOADING"))

        def _do():
            PlayitDownloader.download(on_progress=self._set_progress)

        def _done(_):
            self.progress_frame.hide()
            self._start_tunnel()

        def _err(error):
            self.progress_frame.hide()
            self.btn_run.setEnabled(True)
            self.tunnel_log.appendPlainText(_t("BORE_DL_ERR", error=error))
            self.main.show_toast(_t("BORE_DL_ERR", error=error), True)

        self.main.run_async(_do, _done, _err)

    def _start_tunnel(self):
        self.tunnel_log.clear()
        self.tunnel_log.appendPlainText(_t("BORE_STATUS_CONNECTING"))
        ok = self.manager.toggle_tunnel(self._server_port, self.bridge.on_tunnel_output)
        if not ok:
            self.btn_run.setEnabled(True)
            self.tunnel_log.appendPlainText(_t("BORE_START_ERR"))
            self.main.show_toast(_t("BORE_START_ERR"), True)
            return
        self._update_ui_state()

    # ── Signals ──────────────────────────────────────────────────────────────

    @Slot(str, str)
    def on_tunnel_data(self, line: str, pub_ip: str):
        if line:
            self.tunnel_log.appendPlainText(line)
            self.tunnel_log.verticalScrollBar().setValue(
                self.tunnel_log.verticalScrollBar().maximum()
            )
            # Only toast on process exit — playit logs benign "error/failed" during IPv6 fallback
            if "playit process exited" in line.lower():
                self.main.show_toast(_t("BORE_CONNECT_ERR"), True)
                QTimer.singleShot(200, self._update_ui_state)

        if pub_ip and pub_ip != self.pub_ip:
            self.pub_ip = pub_ip
            self.lbl_pub.setText(pub_ip)
            self.lbl_pub.setStyleSheet(
                f"font-size: 17px; font-weight: 700; color: {COLOR_ACCENT};"
                " background: transparent; border: none;"
            )
            self.btn_copy_pub.setEnabled(True)
            self.tunnel_status_lbl.setText(_t("BORE_STATUS_ACTIVE"))

    def _sync_tunnel_state(self):
        running = bool(self.manager.tunnel_instance and self.manager.tunnel_instance.process)
        if self.is_running != running:
            self._update_ui_state()

    def go_back(self):
        self.tunnel_watchdog.stop()
        self.main.show_settings(self.current_server)
