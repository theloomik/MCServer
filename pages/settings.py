from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QScrollArea,
    QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

import core
from styles import (
    COLOR_ACCENT, COLOR_BG_CARD, COLOR_BORDER, COLOR_DANGER,
    COLOR_TEXT_MAIN, COLOR_TEXT_SEC, disable_wheel_value_change,
)
from translations import _t
from widgets import ModernButton


def _divider(color=None):
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background-color: {color or COLOR_BORDER}; border: none;")
    return line


class SettingsPage(QWidget):
    def __init__(self, manager, main):
        super().__init__()
        self.manager = manager
        self.main = main
        self.current_server = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(0)

        # --- Header ---
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
        layout.addSpacing(20)
        layout.addWidget(_divider())
        layout.addSpacing(20)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        self.form = QVBoxLayout(container)
        self.form.setSpacing(20)
        self.form.setContentsMargins(0, 0, 0, 0)

        # --- Cards row ---
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)

        # RAM card
        ram_card = QFrame()
        ram_card.setFixedHeight(290)
        ram_card.setMaximumWidth(520)
        ram_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        ram_card.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; border-radius: 16px; border: 1px solid {COLOR_BORDER};"
        )
        rl = QVBoxLayout(ram_card)
        rl.setContentsMargins(24, 22, 24, 22)
        rl.setSpacing(0)

        ram_hdr = QHBoxLayout()
        ram_hdr.setSpacing(8)
        lbl_icon = QLabel("🖥")
        lbl_icon.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        ram_hdr.addWidget(lbl_icon)
        ram_hdr_lbl = QLabel(_t("SETTINGS_SECTION_GENERAL"))
        ram_hdr_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLOR_TEXT_MAIN}; background: transparent; border: none;"
        )
        ram_hdr.addWidget(ram_hdr_lbl)
        ram_hdr.addStretch()
        rl.addLayout(ram_hdr)
        rl.addSpacing(12)
        rl.addWidget(_divider())
        rl.addSpacing(14)

        ram_sub = QLabel(_t("SETTINGS_RAM_ALLOC"))
        ram_sub.setStyleSheet(
            f"color: {COLOR_TEXT_SEC}; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        rl.addWidget(ram_sub)
        rl.addSpacing(4)

        self.ram_val = QLabel(_t("RAM_VALUE_GB", value=2))
        self.ram_val.setStyleSheet(
            f"font-size: 30px; font-weight: 800; color: {COLOR_ACCENT}; background: transparent; border: none;"
        )
        rl.addWidget(self.ram_val)
        rl.addSpacing(8)

        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setRange(1, 16)
        disable_wheel_value_change(self.ram_slider)
        self.ram_slider.valueChanged.connect(
            lambda v: self.ram_val.setText(_t("RAM_VALUE_GB", value=v))
        )
        rl.addWidget(self.ram_slider)

        mm = QHBoxLayout()
        mm.addWidget(QLabel("1 GB", styleSheet=f"color:{COLOR_TEXT_SEC}; font-size: 11px; background: transparent; border: none;"))
        mm.addStretch()
        mm.addWidget(QLabel("16 GB", styleSheet=f"color:{COLOR_TEXT_SEC}; font-size: 11px; background: transparent; border: none;"))
        rl.addLayout(mm)
        rl.addSpacing(12)

        btn_save_ram = ModernButton(_t("SETTINGS_BTN_SAVE_RAM"), bg_color=COLOR_ACCENT, text_color="black", is_accent=True)
        btn_save_ram.clicked.connect(self.save_ram)
        rl.addWidget(btn_save_ram)
        cards_row.addWidget(ram_card)

        # Network card
        net_card = QFrame()
        net_card.setFixedHeight(290)
        net_card.setMaximumWidth(520)
        net_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        net_card.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; border-radius: 16px; border: 1px solid {COLOR_BORDER};"
        )
        nl = QVBoxLayout(net_card)
        nl.setContentsMargins(24, 22, 24, 22)
        nl.setSpacing(0)

        net_hdr = QHBoxLayout()
        net_hdr.setSpacing(8)
        net_icon = QLabel("🌐")
        net_icon.setStyleSheet("font-size: 18px; background: transparent; border: none;")
        net_hdr.addWidget(net_icon)
        net_hdr_lbl = QLabel(_t("SETTINGS_SECTION_NETWORK"))
        net_hdr_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLOR_TEXT_MAIN}; background: transparent; border: none;"
        )
        net_hdr.addWidget(net_hdr_lbl)
        net_hdr.addStretch()
        nl.addLayout(net_hdr)
        nl.addSpacing(12)
        nl.addWidget(_divider())
        nl.addSpacing(14)

        net_desc = QLabel(_t("SETTINGS_NETWORK_DESC"))
        net_desc.setStyleSheet(
            f"color: {COLOR_TEXT_SEC}; font-size: 13px; background: transparent; border: none;"
        )
        net_desc.setWordWrap(True)
        nl.addWidget(net_desc)
        nl.addStretch()

        btn_net = ModernButton(_t("SETTINGS_BTN_OPEN_NETWORK"), bg_color="#27272a")
        btn_net.clicked.connect(lambda: self.main.show_network(self.current_server))
        nl.addWidget(btn_net)

        cards_row.addWidget(net_card)
        cards_row.addStretch()
        self.form.addLayout(cards_row)
        self.form.addStretch()

        # --- Danger zone ---
        self.form.addWidget(_divider())
        danger_lbl = QLabel(_t("SETTINGS_SECTION_DANGER"))
        danger_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLOR_DANGER}; margin-top: 4px; background: transparent; border: none;"
        )
        self.form.addWidget(danger_lbl)

        self.btn_delete = ModernButton(
            _t("SETTINGS_BTN_DELETE"),
            bg_color="#2c1515",
            text_color=COLOR_DANGER,
            hover_color="#3d1a1a",
        )
        self.btn_delete.setMaximumWidth(420)
        self.btn_delete.clicked.connect(self.delete_server)
        self.form.addWidget(self.btn_delete)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def load(self, name):
        self.current_server = name
        server = self.manager.servers[name]
        self.ram_slider.setValue(server.ram // 1024)

    def save_ram(self):
        self.manager.servers[self.current_server].ram = self.ram_slider.value() * 1024
        self.manager.save_servers()
        self.main.show_toast(_t("SETTINGS_MSG_RAM_UPDATED"), False)

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
