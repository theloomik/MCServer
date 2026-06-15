from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QLineEdit, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from styles import (
    COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_BG_CARD, COLOR_TEXT_SEC,
    disable_wheel_value_change,
)
from translations import _t
from widgets import ModernButton


class CreatePage(QWidget):
    def __init__(self, manager, main):
        super().__init__()
        self.manager = manager
        self.main = main

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        card = QFrame()
        card.setFixedSize(500, 550)
        card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 16px;")
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 10)
        card.setGraphicsEffect(shadow)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(40, 40, 40, 40)
        cl.setSpacing(20)

        title = QLabel(_t("CREATE_TITLE"))
        title.setStyleSheet("font-size: 26px; font-weight: 800; border: none; background: transparent;")
        cl.addWidget(title)

        self.inp_name = QLineEdit()
        self.inp_name.setPlaceholderText(_t("CREATE_PH_NAME"))
        self.inp_name.setStyleSheet("background-color: #1a1a1f; border: 1px solid #3f3f46; border-radius: 8px; padding: 10px 12px;")
        cl.addWidget(self.inp_name)

        jar_row = QHBoxLayout()
        self.inp_jar = QLineEdit()
        self.inp_jar.setPlaceholderText(_t("CREATE_PH_JAR"))
        self.inp_jar.setStyleSheet("background-color: #1a1a1f; border: 1px solid #3f3f46; border-radius: 8px; padding: 10px 12px;")
        btn_file = ModernButton("📂", bg_color="#27272a")
        btn_file.setFixedWidth(50)
        btn_file.setStyleSheet(btn_file.styleSheet() + "QPushButton { padding: 0px; font-size: 18px; }")
        btn_file.clicked.connect(self.browse)
        jar_row.addWidget(self.inp_jar)
        jar_row.addWidget(btn_file)
        cl.addLayout(jar_row)

        self.lbl_ram = QLabel(_t("CREATE_RAM_LABEL", value=2))
        self.lbl_ram.setStyleSheet(f"border:none; background:transparent; font-weight:600; color: {COLOR_ACCENT};")
        cl.addWidget(self.lbl_ram)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(1, 16)
        self.slider.setValue(2)
        disable_wheel_value_change(self.slider)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(1)
        self.slider.valueChanged.connect(lambda v: self.lbl_ram.setText(_t("CREATE_RAM_LABEL", value=v)))
        cl.addWidget(self.slider)

        slider_labels = QHBoxLayout()
        slider_labels.setContentsMargins(0, 0, 0, 0)
        slider_labels.addWidget(QLabel(_t("RAM_MIN_LABEL"), styleSheet=f"color: {COLOR_TEXT_SEC};"))
        slider_labels.addStretch()
        slider_labels.addWidget(QLabel(_t("RAM_MAX_LABEL"), styleSheet=f"color: {COLOR_TEXT_SEC};"))
        cl.addLayout(slider_labels)
        cl.addStretch()

        self.btn_create = ModernButton(
            _t("CREATE_BTN_CREATE"), bg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER, text_color="white", is_accent=True,
        )
        self.btn_create.clicked.connect(self.create)
        cl.addWidget(self.btn_create)

        btn_cancel = ModernButton(_t("CREATE_BTN_CANCEL"), bg_color="transparent")
        btn_cancel.clicked.connect(self.main.show_home)
        cl.addWidget(btn_cancel)

        layout.addWidget(card)

    def browse(self):
        f, _ = QFileDialog.getOpenFileName(self, _t("CREATE_DLG_PICK_JAR"), "", "*.jar")
        if f:
            self.inp_jar.setText(f)

    def create(self):
        name = self.inp_name.text()
        jar = self.inp_jar.text()
        if not name or not jar:
            self.main.show_toast(_t("CREATE_MSG_FILL_FIELDS"), True)
            return
        self.btn_create.setEnabled(False)
        ram_mb = self.slider.value() * 1024
        self.main.run_async(
            lambda: self.manager.create_server(name, jar, ram_mb),
            lambda created: self._on_done(name, created),
            lambda _err: self._on_done(name, False),
        )

    def _on_done(self, name, created):
        self.btn_create.setEnabled(True)
        if created:
            self.main.refresh_sidebar()
            self.main.show_dashboard(name)
            self.main.show_toast(_t("CREATE_MSG_CREATED", name=name), False)
        else:
            self.main.show_toast(_t("CREATE_MSG_CREATE_ERR"), True)
