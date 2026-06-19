import datetime
import html
import os
import re
from collections import deque

from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

import core
from styles import (
    COLOR_ACCENT, COLOR_BG_CARD, COLOR_DANGER, COLOR_TEXT_SEC, strip_ansi,
)
from translations import _t
from widgets import FilterButton, MetricCard, ModernButton, StatusBadge


class DashboardPage(QWidget):
    def __init__(self, manager, bridge, main):
        super().__init__()
        self.manager = manager
        self.bridge = bridge
        self.main = main
        self.current_server = None
        self.kill_timer = QTimer(self)
        self.kill_timer.setInterval(5000)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.enable_kill_mode)

        self.console_history = {}
        self.is_restarting = False
        self.log_history = deque(maxlen=5000)
        self.filter_info = True
        self.filter_warn = True
        self.filter_error = True

        self._setup_ui()
        self._connect_bridge()

    def _setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)

        left_col = QVBoxLayout()
        left_col.setSpacing(20)

        # --- Header ---
        header_frame = QFrame()
        header_frame.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(25, 25, 25, 25)

        top_row = QHBoxLayout()
        self.title_lbl = QLabel(_t("DASH_TITLE_DEFAULT"))
        self.title_lbl.setStyleSheet("font-size: 32px; font-weight: 800; color: white; background: transparent;")
        self.title_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.status_badge = StatusBadge("OFFLINE")
        top_row.addWidget(self.title_lbl)
        top_row.addWidget(self.status_badge)
        header_layout.addLayout(top_row)

        self.desc_lbl = QLabel(_t("DASH_DESC_UNKNOWN"))
        self.desc_lbl.setStyleSheet(f"font-size: 14px; color: {COLOR_TEXT_SEC}; font-weight: 500; background: transparent; margin-bottom: 10px;")
        header_layout.addWidget(self.desc_lbl)

        stats_row = QHBoxLayout()
        self.uptime_lbl = QLabel(_t("DASH_UPTIME_ZERO"))
        self.uptime_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 13px; margin-right: 15px;")
        self.players_lbl = QLabel(_t("DASH_PLAYERS_DEFAULT"))
        self.players_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 13px;")
        stats_row.addWidget(self.uptime_lbl)
        stats_row.addWidget(self.players_lbl)
        stats_row.addStretch()
        header_layout.addLayout(stats_row)
        header_layout.addSpacing(15)

        btn_row = QHBoxLayout()
        self.btn_start = ModernButton(_t("DASH_BTN_START"), bg_color=COLOR_BG_CARD, text_color="white", is_accent=True)
        self.btn_start.setMinimumWidth(180)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_stop = ModernButton(_t("DASH_BTN_STOP"), bg_color=COLOR_BG_CARD, text_color="white", is_danger=True)
        self.btn_stop.setMinimumWidth(150)
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_restart = ModernButton(_t("DASH_BTN_RESTART"), bg_color="#18181b")
        self.btn_restart.setMinimumWidth(160)
        self.btn_restart.clicked.connect(self.on_restart)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_restart)
        btn_row.addStretch()
        header_layout.addLayout(btn_row)
        left_col.addWidget(header_frame)

        # --- Console ---
        console_wrapper = QFrame()
        console_wrapper.setStyleSheet("background-color: #0c0c0e; border-radius: 12px;")
        cw_layout = QVBoxLayout(console_wrapper)
        cw_layout.setContentsMargins(0, 0, 0, 0)
        cw_layout.setSpacing(0)

        term_header = QFrame()
        term_header.setStyleSheet("background-color: #18181b; border-bottom: 1px solid #27272a; border-top-left-radius: 12px; border-top-right-radius: 12px;")
        th_layout = QHBoxLayout(term_header)
        th_layout.setContentsMargins(10, 5, 10, 5)
        th_layout.setSpacing(10)
        th_layout.addWidget(QLabel(_t("DASH_TERMINAL_TITLE"), styleSheet="color: #a1a1aa; font-weight: bold; font-family: Consolas;"))
        th_layout.addStretch()

        self.btn_filter_info = FilterButton(_t("FILTER_INFO"), "#a1a1aa")
        self.btn_filter_info.clicked.connect(lambda: self.toggle_filter("INFO"))
        self.btn_filter_warn = FilterButton(_t("FILTER_WARN"), "#f59e0b")
        self.btn_filter_warn.clicked.connect(lambda: self.toggle_filter("WARN"))
        self.btn_filter_error = FilterButton(_t("FILTER_ERR"), "#ef4444")
        self.btn_filter_error.clicked.connect(lambda: self.toggle_filter("ERROR"))
        th_layout.addWidget(self.btn_filter_info)
        th_layout.addWidget(self.btn_filter_warn)
        th_layout.addWidget(self.btn_filter_error)

        sep = QFrame()
        sep.setFixedWidth(1)
        sep.setFixedHeight(20)
        sep.setStyleSheet("background: #27272a;")
        th_layout.addWidget(sep)

        btn_save = ModernButton(_t("DASH_BTN_SAVE_LOG"), bg_color="transparent", hover_color="#27272a")
        btn_save.setMinimumWidth(132)
        btn_save.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_save.setFixedHeight(30)
        btn_save.clicked.connect(self.save_log)
        btn_save.setToolTip(_t("DASH_TIP_SAVE_LOG"))

        btn_clear = ModernButton(_t("DASH_BTN_CLEAR_LOG"), bg_color="transparent", hover_color="#27272a")
        btn_clear.setMinimumWidth(132)
        btn_clear.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_clear.setFixedHeight(30)
        btn_clear.clicked.connect(self.clear_console)
        btn_clear.setToolTip(_t("DASH_TIP_CLEAR_LOG"))

        th_layout.addWidget(btn_save)
        th_layout.addWidget(btn_clear)
        cw_layout.addWidget(term_header)

        self.console_out = QPlainTextEdit()
        self.console_out.setPlaceholderText(_t("DASH_PH_CONSOLE"))
        self.console_out.setStyleSheet("border: none; border-radius: 0px; background: transparent;")
        self.console_out.setReadOnly(True)
        cw_layout.addWidget(self.console_out)

        input_bar = QFrame()
        input_bar.setStyleSheet("background-color: #18181b; border-top: 1px solid #27272a; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        ib_layout = QHBoxLayout(input_bar)
        ib_layout.setContentsMargins(10, 10, 10, 10)
        self.inp_cmd = QLineEdit()
        self.inp_cmd.setPlaceholderText(_t("DASH_PH_CMD"))
        self.inp_cmd.setStyleSheet("background-color: #09090b; border: 1px solid #27272a;")
        self.inp_cmd.returnPressed.connect(self.send_cmd)
        btn_send = ModernButton(_t("DASH_BTN_SEND"), bg_color="#27272a")
        btn_send.setMinimumWidth(140)
        btn_send.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_send.clicked.connect(self.send_cmd)
        ib_layout.addWidget(self.inp_cmd)
        ib_layout.addWidget(btn_send)
        cw_layout.addWidget(input_bar)
        left_col.addWidget(console_wrapper, stretch=1)

        # --- Right column (metrics) ---
        right_col = QVBoxLayout()
        right_col.setSpacing(15)

        lbl_ctrl = QLabel(_t("DASH_SECTION_CONTROL"))
        lbl_ctrl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-weight: bold; font-size: 12px; letter-spacing: 1px;")
        right_col.addWidget(lbl_ctrl)
        btn_props = ModernButton(_t("DASH_BTN_PROPS"), bg_color="#18181b")
        btn_props.clicked.connect(lambda: self.main.show_properties(self.current_server))
        right_col.addWidget(btn_props)
        btn_settings = ModernButton(_t("DASH_BTN_SETTINGS"), bg_color="#18181b")
        btn_settings.clicked.connect(lambda: self.main.show_settings(self.current_server))
        right_col.addWidget(btn_settings)
        btn_folder = ModernButton(_t("DASH_BTN_FOLDER"), bg_color="#18181b")
        btn_folder.clicked.connect(self.open_folder)
        right_col.addWidget(btn_folder)
        right_col.addSpacing(20)

        lbl_mon = QLabel(_t("DASH_SECTION_MONITOR"))
        lbl_mon.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-weight: bold; font-size: 12px; letter-spacing: 1px;")
        right_col.addWidget(lbl_mon)

        scroll_stats = QScrollArea()
        scroll_stats.setWidgetResizable(True)
        scroll_stats.setStyleSheet("background: transparent; border: none;")
        scroll_stats.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        scroll_stats.setMinimumWidth(340)

        stats_container = QWidget()
        stats_grid = QGridLayout(stats_container)
        stats_grid.setSpacing(12)
        stats_grid.setContentsMargins(0, 0, 0, 0)
        stats_grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.card_cpu = MetricCard("CPU", "💻", " %", color="#0ea5e9")
        stats_grid.addWidget(self.card_cpu, 0, 0)
        self.card_ram = MetricCard("RAM", "🧠", " MB", color="#8b5cf6")
        stats_grid.addWidget(self.card_ram, 0, 1)
        self.card_disk = MetricCard("DISK", "💾", " GB", color="#f59e0b", minimal=True)
        stats_grid.addWidget(self.card_disk, 1, 0)
        self.card_tps = MetricCard("TPS", "⏱", "", color="#10b981")
        stats_grid.addWidget(self.card_tps, 1, 1)

        scroll_stats.setWidget(stats_container)
        right_col.addWidget(scroll_stats)

        main_layout.addLayout(left_col, stretch=7)
        main_layout.addLayout(right_col, stretch=3)

    def _connect_bridge(self):
        self.bridge.log_signal.connect(self.on_log)
        self.bridge.stats_signal.connect(self.on_stats)
        self.bridge.state_signal.connect(self.on_state_change)
        self.bridge.stop_signal.connect(self.on_process_stop)

    # --- Filter & console ---

    def toggle_filter(self, type_):
        if type_ == "INFO":
            self.filter_info = self.btn_filter_info.toggle()
        elif type_ == "WARN":
            self.filter_warn = self.btn_filter_warn.toggle()
        elif type_ == "ERROR":
            self.filter_error = self.btn_filter_error.toggle()
        self.refresh_console_view()

    def refresh_console_view(self):
        self.console_out.clear()
        logs = list(self.log_history)[-2000:]
        for text, type_ in logs:
            if self._should_show(type_):
                self._append_to_widget(text, type_)
        sb = self.console_out.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _should_show(self, type_):
        if type_ == "INFO" and not self.filter_info:
            return False
        if type_ == "WARN" and not self.filter_warn:
            return False
        if type_ == "ERROR" and not self.filter_error:
            return False
        return True

    def _append_to_widget(self, text, type_):
        color = "#e4e4e7"
        if type_ == "WARN":
            color = "#fbbf24"
        elif type_ == "ERROR":
            color = "#ef4444"
        self.console_out.appendHtml(f'<span style="color:{color};">{html.escape(text)}</span>')

    def clear_console(self):
        self.console_out.clear()
        self.log_history.clear()

    def save_log(self):
        if not self.log_history:
            self.main.show_toast(_t("DASH_MSG_LOG_EMPTY"), True)
            return
        fname, _ = QFileDialog.getSaveFileName(
            self, _t("DASH_TIP_SAVE_LOG"),
            f"server_log_{datetime.datetime.now().strftime('%H-%M-%S')}.txt",
            "Text Files (*.txt)",
        )
        if fname:
            try:
                with open(fname, "w", encoding="utf-8") as f:
                    for text, _ in self.log_history:
                        f.write(text + "\n")
                self.main.show_toast(_t("DASH_MSG_LOG_SAVED"), False)
            except Exception:
                self.main.show_toast(_t("DASH_MSG_LOG_SAVE_ERR"), True)

    # --- Load ---

    def load(self, name):
        if name not in self.manager.servers:
            self.main.show_home()
            self.main.show_toast(_t("DASH_MSG_FOLDER_ERR"), True)
            return
        if self.current_server != name:
            self.clear_console()
            self.current_server = name

        server = self.manager.servers[name]
        self.title_lbl.setText(server.name)
        c_type, c_ver, _ = core.parse_core_info(server.core_name)
        self.desc_lbl.setText(_t("DASH_DESC_CORE_VER", core=c_type, ver=c_ver))

        # Show placeholders; real values arrive from async I/O below
        self.players_lbl.setText(_t("DASH_PLAYERS_DEFAULT"))
        self.uptime_lbl.setText(_t("DASH_UPTIME_ZERO"))

        state = "OFFLINE"
        if self.manager.active_instance and self.manager.active_instance.data.name == name:
            state = self.manager.active_instance.state
        self.update_ui_state(state)
        if state == "OFFLINE":
            for c in [self.card_tps, self.card_ram, self.card_cpu]:
                c.update_data(-1.0, 100)

        # Both properties read and disk scan run off the main thread
        def _load_io():
            props = self.manager.get_server_properties(name)
            size = core.ServerManager.get_dir_size_gb(server.directory)
            return props, size

        def _on_loaded(result):
            if self.current_server != name:
                return
            props, size = result
            max_p = props.get("max-players", "20")
            self.players_lbl.setText(_t("DASH_PLAYERS", cur=0, max_p=max_p))
            self.on_disk_size_loaded(name, size)

        self.main.run_async(_load_io, _on_loaded)

    def on_disk_size_loaded(self, server_name, size):
        if self.current_server == server_name:
            self.card_disk.update_data(size, 0, f"{size:.2f} GB")

    # --- UI state ---

    def update_ui_state(self, state):
        self.status_badge.update_state(state)
        self.btn_restart.setEnabled(state == "ONLINE")
        if state == "OFFLINE":
            self.btn_start.setEnabled(True)
            self.btn_start.setText(_t("DASH_BTN_START"))
            self.btn_stop.setEnabled(False)
            self.btn_stop.setText(_t("DASH_BTN_STOP"))
            if self.manager.active_instance and self.manager.active_instance.state != "OFFLINE":
                if self.manager.active_instance.data.name != self.current_server:
                    self.btn_start.setEnabled(False)
                    self.btn_start.setText(_t("DASH_BTN_BUSY"))
        elif state == "STARTING":
            self.btn_start.setEnabled(False)
            self.btn_start.setText(_t("DASH_BTN_STARTING"))
            self.btn_stop.setEnabled(True)
        elif state == "ONLINE":
            self.btn_start.setEnabled(False)
            self.btn_start.setText(_t("DASH_BTN_RUNNING"))
            self.btn_stop.setEnabled(True)
        elif state == "STOPPING":
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_stop.setText(_t("DASH_BTN_STOPPING"))

    @Slot(str)
    def on_state_change(self, state):
        if self.current_server and self.manager.active_instance:
            if self.manager.active_instance.data.name == self.current_server:
                self.update_ui_state(state)

    @Slot(str, str)
    def on_log(self, text, type_):
        if not self.current_server:
            return
        if "TPS from last" in text:
            return
        if self.manager.active_instance and self.manager.active_instance.data.name == self.current_server:
            clean = strip_ansi(text.strip())
            if not clean:
                return
            self.log_history.append((clean, type_))
            if self._should_show(type_):
                self._append_to_widget(clean, type_)
                sb = self.console_out.verticalScrollBar()
                sb.setValue(sb.maximum())

    @Slot(float, float, float, str, int, float)
    def on_stats(self, ram, tps, disk, uptime, players, cpu):
        if not self.current_server:
            return
        if self.manager.active_instance and self.manager.active_instance.data.name == self.current_server:
            max_ram = self.manager.active_instance.data.ram
            self.card_ram.update_data(ram, max_ram, f"{int(ram)} / {max_ram} MB")
            self.card_tps.update_data(tps, 20)
            self.card_disk.update_data(disk, 0, f"{disk:.2f} GB")
            self.card_cpu.update_data(cpu, 100, f"{cpu:.1f} %")
            self.uptime_lbl.setText(_t("DASH_UPTIME", uptime=uptime))
            current_text = self.players_lbl.text()
            if "/" in current_text:
                max_p = current_text.split("/")[1].strip()
                self.players_lbl.setText(_t("DASH_PLAYERS", cur=players, max_p=max_p))

    @Slot(int)
    def on_process_stop(self, code):
        msg = _t("DASH_MSG_PROCESS_EXIT", code=code)
        self.log_history.append((msg, "INFO"))
        self._append_to_widget(msg, "INFO")

        self.kill_timer.stop()
        for c in [self.card_tps, self.card_ram, self.card_cpu]:
            c.update_data(-1.0, 100)
        _lbl = self.players_lbl.text()
        _m = re.search(r'\d+', _lbl)
        if _m:
            self.players_lbl.setText(_lbl.replace(_m.group(), "0", 1))
        self.uptime_lbl.setText(_t("DASH_UPTIME_ZERO"))

        if self.is_restarting:
            self.is_restarting = False
            QTimer.singleShot(1000, self.on_start)

    # --- Actions ---

    def on_start(self):
        if not self.current_server:
            return
        server = self.manager.servers[self.current_server]
        if core.ServerInstance.needs_eula(server.directory):
            answer = QMessageBox.question(
                self, _t("EULA_TITLE"), _t("EULA_TEXT"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            core.ServerInstance.write_eula(server.directory)
        self.clear_console()
        self.console_history[self.current_server] = ""
        cb = core.ServerCallbacks(
            self.bridge.on_log, self.bridge.on_stats,
            self.bridge.on_state, self.bridge.on_stop,
        )
        self.manager.start_instance(self.current_server, cb)

    def on_stop(self):
        if self.btn_stop.text() == _t("DASH_BTN_KILL"):
            self.manager.kill_instance()
            self.btn_stop.setText(_t("DASH_BTN_KILLED"))
            self.btn_stop.setEnabled(False)
            return
        self.manager.stop_instance()
        self.kill_timer.start()

    def on_restart(self):
        self.is_restarting = True
        self.on_stop()

    def enable_kill_mode(self):
        if self.manager.active_instance and self.manager.active_instance.state != "OFFLINE":
            self.btn_stop.setEnabled(True)
            self.btn_stop.setText(_t("DASH_BTN_KILL"))
            self.btn_stop.setStyleSheet(
                f"background-color: {COLOR_DANGER}; color: white; border: none; "
                "border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;"
            )

    def send_cmd(self):
        cmd = self.inp_cmd.text()
        if cmd:
            self.manager.send_command(cmd)
            entry = (f"> {cmd}", "INFO")
            self.log_history.append(entry)
            self._append_to_widget(*entry)
            self.inp_cmd.clear()

    def open_folder(self):
        if self.current_server:
            path = self.manager.servers[self.current_server].directory
            try:
                server_dir = self.manager.path_policy.require_managed_directory(path)
                if not server_dir.is_dir():
                    raise OSError("Server directory is missing")
                os.startfile(server_dir)  # nosec B606 — path validated by require_managed_directory
            except Exception:
                self.main.show_toast(_t("DASH_MSG_FOLDER_ERR"), True)
