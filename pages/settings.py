from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QScrollArea,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

import core
from styles import (
    COLOR_BG_CARD, COLOR_BORDER, COLOR_DANGER, COLOR_TEXT_MAIN, COLOR_TEXT_SEC,
    disable_wheel_value_change,
)
from translations import _t
from widgets import ModernButton


class SettingsPage(QWidget):
    def __init__(self, manager, main):
        super().__init__()
        self.manager = manager
        self.main = main
        self.current_server = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        h = QHBoxLayout()
        btn_back = ModernButton(_t("SETTINGS_BACK"), bg_color="#27272a")
        btn_back.setFixedWidth(90)
        btn_back.clicked.connect(self.go_back)
        title = QLabel(_t("SETTINGS_TITLE"))
        title.setStyleSheet("font-size: 24px; font-weight: 800; margin-left: 20px;")
        h.addWidget(btn_back)
        h.addWidget(title)
        h.addStretch()
        layout.addLayout(h)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        self.form = QVBoxLayout(container)
        self.form.setSpacing(20)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)

        # RAM card
        ram_card = QFrame()
        ram_card.setMaximumWidth(520)
        ram_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        ram_card.setFixedHeight(260)
        ram_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        rl = QVBoxLayout(ram_card)
        rl.setContentsMargins(20, 20, 20, 20)
        rl.addWidget(QLabel(_t("SETTINGS_SECTION_GENERAL"), styleSheet=f"font-size: 16px; font-weight: 700; color: {COLOR_TEXT_MAIN};"))
        self.ram_val = QLabel(_t("RAM_VALUE_GB", value=2))
        self.ram_val.setStyleSheet("font-size: 18px; font-weight: bold; color: white;")
        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setRange(1, 16)
        disable_wheel_value_change(self.ram_slider)
        self.ram_slider.valueChanged.connect(lambda v: self.ram_val.setText(_t("RAM_VALUE_GB", value=v)))
        rl.addWidget(QLabel(_t("SETTINGS_RAM_ALLOC"), styleSheet=f"color:{COLOR_TEXT_SEC}; font-weight:600;"))
        rl.addWidget(self.ram_val)
        rl.addWidget(self.ram_slider)
        btn_save_ram = ModernButton(_t("SETTINGS_BTN_SAVE_RAM"), bg_color="#27272a")
        btn_save_ram.clicked.connect(self.save_ram)
        rl.addWidget(btn_save_ram)
        cards_row.addWidget(ram_card)

        # Network card
        net_card = QFrame()
        net_card.setMaximumWidth(520)
        net_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        net_card.setFixedHeight(260)
        net_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        nl = QVBoxLayout(net_card)
        nl.setContentsMargins(20, 20, 20, 20)
        nl.addWidget(QLabel(_t("SETTINGS_SECTION_NETWORK"), styleSheet=f"font-size: 16px; font-weight: 700; color: {COLOR_TEXT_MAIN};"))
        nl.addWidget(QLabel(_t("SETTINGS_NETWORK_DESC"), styleSheet=f"color:{COLOR_TEXT_SEC};"))
        btn_net = ModernButton(_t("SETTINGS_BTN_OPEN_NETWORK"), bg_color="#27272a")
        btn_net.clicked.connect(lambda: self.main.show_network(self.current_server))
        nl.addWidget(btn_net)
        cards_row.addWidget(net_card)
        cards_row.addStretch()
        self.form.addLayout(cards_row)

        # Language card
        lang_wrap = QHBoxLayout()
        lang_wrap.setContentsMargins(0, 0, 0, 0)
        lang_card = QFrame()
        lang_card.setMaximumWidth(520)
        lang_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lang_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px; border: 1px solid {COLOR_BORDER};")
        ll = QVBoxLayout(lang_card)
        ll.setContentsMargins(20, 18, 20, 18)
        ll.setSpacing(10)
        ll.addWidget(QLabel(_t("SETTINGS_SECTION_LANGUAGE"), styleSheet=f"font-size: 16px; font-weight: 700; color: {COLOR_TEXT_MAIN};"))
        lang_row = QHBoxLayout()
        lang_row.setSpacing(12)
        lang_row.addWidget(QLabel(_t("SETTINGS_LANGUAGE_LABEL"), styleSheet=f"color:{COLOR_TEXT_SEC}; font-weight:600;"))
        lang_row.addStretch()
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(_t("SETTINGS_LANG_UK"), "uk")
        self.lang_combo.addItem(_t("SETTINGS_LANG_EN"), "en")
        self.lang_combo.setMinimumWidth(180)
        disable_wheel_value_change(self.lang_combo)
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        lang_row.addWidget(self.lang_combo)
        ll.addLayout(lang_row)
        lang_wrap.addWidget(lang_card)
        lang_wrap.addStretch()
        self.form.addLayout(lang_wrap)

        self.form.addStretch()
        self._add_header(_t("SETTINGS_SECTION_DANGER"))
        self.btn_delete = ModernButton(_t("SETTINGS_BTN_DELETE"), bg_color="#2c1515", text_color=COLOR_DANGER, hover_color=COLOR_DANGER)
        self.btn_delete.clicked.connect(self.delete_server)
        self.form.addWidget(self.btn_delete)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def _add_header(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_TEXT_SEC}; margin-top: 10px;")
        self.form.addWidget(lbl)

    def load(self, name):
        self.current_server = name
        server = self.manager.servers[name]
        self.ram_slider.setValue(server.ram // 1024)
        lang = self.manager.settings.get("language", "uk")
        idx = self.lang_combo.findData(lang)
        self.lang_combo.blockSignals(True)
        self.lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.lang_combo.blockSignals(False)

    def save_ram(self):
        self.manager.servers[self.current_server].ram = self.ram_slider.value() * 1024
        self.manager.save_servers()
        self.main.show_toast(_t("SETTINGS_MSG_RAM_UPDATED"), False)

    def on_language_changed(self):
        lang = self.lang_combo.currentData()
        self.manager.set_language(lang)
        self.main.show_toast(_t("SETTINGS_LANG_RESTART"), False)

    def delete_server(self):
        active = self.manager.active_instance
        if active and active.data.name == self.current_server and active.state != core.ServerState.OFFLINE:
            self.main.show_toast(_t("SETTINGS_MSG_STOP_BEFORE_DELETE"), True)
            return
        answer = QMessageBox.question(
            self, _t("SETTINGS_DELETE_CONFIRM_TITLE"),
            _t("SETTINGS_DELETE_CONFIRM_TEXT", name=self.current_server),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.btn_delete.setEnabled(False)
        self.main.run_async(
            lambda name=self.current_server: self.manager.delete_server(name),
            self._on_delete_done,
            lambda _err: self._on_delete_done(False),
        )

    def _on_delete_done(self, deleted):
        self.btn_delete.setEnabled(True)
        if deleted:
            self.main.show_home()
            self.main.show_toast(_t("SETTINGS_MSG_SERVER_DELETED"), False)
        else:
            self.main.show_toast(_t("SETTINGS_MSG_DELETE_FAILED"), True)

    def go_back(self):
        self.main.show_dashboard(self.current_server)
