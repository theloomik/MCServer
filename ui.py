import sys

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

import core
from pages import CreatePage, DashboardPage, NetworkPage, PropertiesPage, SettingsPage
from styles import (
    COLOR_ACCENT, COLOR_BG_CARD, COLOR_BG_SIDEBAR, COLOR_BORDER,
    COLOR_TEXT_MAIN, COLOR_TEXT_SEC, FONT_FAMILY, STYLESHEET, fade_in,
)
from translations import _t, Translator
from widgets import ServerBridge, ServerListItem, ToastNotification, WorkerTask


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.manager = core.ServerManager()
        Translator().set_language(self.manager.settings.get("language", "uk"))
        self.setWindowTitle(_t("APP_TITLE"))
        self.resize(1300, 800)

        self.bridge = ServerBridge()
        self.thread_pool = QThreadPool.globalInstance()
        self.worker_tasks: set = set()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Sidebar ---
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(260)
        self.sidebar.setStyleSheet(f"background-color: {COLOR_BG_SIDEBAR}; border-right: 1px solid {COLOR_BORDER};")
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(20, 30, 20, 30)
        sb.setSpacing(20)

        logo = QLabel(_t("SIDEBAR_LOGO"))
        logo.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {COLOR_ACCENT};")
        sb.addWidget(logo)

        self.sidebar_search = QLineEdit()
        self.sidebar_search.setPlaceholderText(_t("SIDEBAR_SEARCH"))
        self.sidebar_search.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border: 1px solid {COLOR_BORDER}; padding: 8px; border-radius: 6px; font-size: 12px;")
        self.sidebar_search.textChanged.connect(self._filter_sidebar)
        sb.addWidget(self.sidebar_search)

        sb.addWidget(QLabel(_t("SIDEBAR_ALL_SERVERS"), styleSheet=f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 700; letter-spacing: 1px; margin-top: 10px;"))

        self.server_list_scroll = QScrollArea()
        self.server_list_scroll.setWidgetResizable(True)
        self.server_list_scroll.setStyleSheet("background: transparent; border: none;")
        self.server_list_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.server_list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.server_list_container = QWidget()
        self.server_list_layout = QVBoxLayout(self.server_list_container)
        self.server_list_layout.setContentsMargins(0, 0, 0, 0)
        self.server_list_layout.setSpacing(5)
        self.server_list_layout.setAlignment(Qt.AlignTop)
        self.server_list_scroll.setWidget(self.server_list_container)
        sb.addWidget(self.server_list_scroll)

        from widgets import ModernButton as _Btn
        btn_new = _Btn(_t("SIDEBAR_NEW_SERVER"), bg_color="#27272a")
        btn_new.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        sb.addWidget(btn_new)
        main_layout.addWidget(self.sidebar)

        # --- Page stack ---
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: transparent;")

        self.page_dash = DashboardPage(self.manager, self.bridge, self)
        self.page_create = CreatePage(self.manager, self)
        self.page_settings = SettingsPage(self.manager, self)
        self.page_network = NetworkPage(self.manager, self.bridge, self)
        self.page_props = PropertiesPage(self.manager, self)

        self.page_home = QWidget()
        hl = QVBoxLayout(self.page_home)
        hl.setAlignment(Qt.AlignCenter)
        home_title = QLabel(_t("APP_WELCOME_TITLE"))
        home_title.setStyleSheet("font-size: 32px; font-weight: 800; color: #27272a;")
        home_sub = QLabel(_t("APP_WELCOME_SUB"))
        home_sub.setStyleSheet(f"font-size: 16px; color: {COLOR_TEXT_SEC}; margin-top: 10px;")
        hl.addWidget(home_title)
        hl.addWidget(home_sub)

        self.stack.addWidget(self.page_dash)      # 0
        self.stack.addWidget(self.page_create)    # 1
        self.stack.addWidget(self.page_settings)  # 2
        self.stack.addWidget(self.page_network)   # 3
        self.stack.addWidget(self.page_home)      # 4
        self.stack.addWidget(self.page_props)     # 5
        self.stack.setCurrentIndex(4)
        main_layout.addWidget(self.stack)

        self.refresh_sidebar()

    # --- Navigation ---

    def show_dashboard(self, name):
        self.stack.setCurrentIndex(0)
        self.page_dash.load(name)
        fade_in(self.page_dash)

    def show_home(self):
        self.stack.setCurrentIndex(4)
        self.refresh_sidebar()

    def show_settings(self, name):
        self.stack.setCurrentIndex(2)
        self.page_settings.load(name)
        fade_in(self.page_settings)

    def show_network(self, name):
        self.stack.setCurrentIndex(3)
        self.page_network.load(name)
        fade_in(self.page_network)

    def show_properties(self, name):
        self.stack.setCurrentIndex(5)
        self.page_props.begin_load(name)
        fade_in(self.page_props)

    def show_toast(self, msg, is_error=False):
        ToastNotification(self, msg, is_error)

    # --- Sidebar ---

    def refresh_sidebar(self):
        for i in reversed(range(self.server_list_layout.count())):
            w = self.server_list_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        for name, server in self.manager.servers.items():
            c_type, c_ver, _ = core.parse_core_info(server.core_name)
            is_running = (
                bool(self.manager.active_instance)
                and self.manager.active_instance.data.name == name
                and self.manager.active_instance.state != "OFFLINE"
            )
            item = ServerListItem(name, f"{c_type} • {c_ver}", is_running, self._on_sidebar_click)
            self.server_list_layout.addWidget(item)

    def _filter_sidebar(self, text):
        text = text.lower()
        for i in range(self.server_list_layout.count()):
            w = self.server_list_layout.itemAt(i).widget()
            if w:
                w.setVisible(text in w.server_name.lower())

    def _on_sidebar_click(self, name):
        self.show_dashboard(name)

    # --- Async runner ---

    def run_async(self, function, on_result, on_error=None):
        task = WorkerTask(function)
        self.worker_tasks.add(task)
        task.signals.result.connect(on_result)
        if on_error:
            task.signals.error.connect(on_error)
        task.signals.finished.connect(lambda: self.worker_tasks.discard(task))
        self.thread_pool.start(task)

    def closeEvent(self, event):
        if self.manager:
            self.manager.cleanup()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont(FONT_FAMILY, 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
