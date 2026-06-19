from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from styles import (
    COLOR_ACCENT, COLOR_ACCENT_HOVER, COLOR_BG_CARD, COLOR_BORDER,
    COLOR_TEXT_SEC, PROPERTY_GUIDE, disable_wheel_value_change,
)
from translations import _t
from widgets import ModernButton


class PropertiesPage(QWidget):
    def __init__(self, manager, main):
        super().__init__()
        self.manager = manager
        self.main = main
        self.current_server = None
        self.widgets_map = {}
        self.card_order = []
        self._pending_server = None
        self._load_seq = 0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        h = QHBoxLayout()
        btn_back = ModernButton(_t("HOME_NAV_BACK"), bg_color="#27272a")
        btn_back.setFixedWidth(90)
        btn_back.clicked.connect(self.go_back)
        title = QLabel(_t("PROPS_TITLE"))
        title.setStyleSheet("font-size: 24px; font-weight: 800; margin-left: 20px;")
        h.addWidget(btn_back)
        h.addWidget(title)
        h.addStretch()
        layout.addLayout(h)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(_t("PROPS_SEARCH"))
        self.search_bar.setFixedHeight(42)
        self.search_bar.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; border: 1px solid {COLOR_BORDER};"
            f" padding: 10px 14px; border-radius: 10px; font-size: 13px;"
        )
        self.search_bar.textChanged.connect(self._filter)
        layout.addWidget(self.search_bar)

        self.loading_lbl = QLabel(_t("PROPS_LOADING"))
        self.loading_lbl.setAlignment(Qt.AlignCenter)
        self.loading_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 14px; font-weight: 600; padding: 14px;")
        self.loading_lbl.hide()
        layout.addWidget(self.loading_lbl)

        self.properties_scroll = QScrollArea()
        self.properties_scroll.setWidgetResizable(True)
        self.properties_scroll.setStyleSheet("background: transparent; border: none;")
        self.container = QWidget()
        self.form = QGridLayout(self.container)
        self.form.setSpacing(15)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.properties_scroll.setWidget(self.container)
        layout.addWidget(self.properties_scroll)

        self.btn_save = ModernButton(_t("PROPS_BTN_SAVE"), bg_color=COLOR_ACCENT, text_color="white", is_accent=True)
        self.btn_save.setFixedHeight(52)
        self.btn_save.setStyleSheet(
            self.btn_save.styleSheet() +
            f"QPushButton {{ background-color: {COLOR_ACCENT_HOVER}; border: 1px solid {COLOR_ACCENT}; font-size: 15px; }}"
        )
        self.btn_save.clicked.connect(self.save_all)
        layout.addWidget(self.btn_save)

    # begin_load / load are aliases
    def load(self, name):
        self.begin_load(name)

    def begin_load(self, name):
        self.current_server = name
        self._pending_server = name
        self._load_seq += 1
        seq = self._load_seq
        self.loading_lbl.show()
        self.properties_scroll.hide()
        self.btn_save.setEnabled(False)
        self.search_bar.setEnabled(False)
        self.search_bar.blockSignals(True)
        self.search_bar.clear()
        self.search_bar.blockSignals(False)
        QTimer.singleShot(10, lambda: self._load_deferred(seq))

    def _load_deferred(self, seq):
        if seq != self._load_seq or not self._pending_server:
            return
        while self.form.count():
            item = self.form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.widgets_map = {}
        self.card_order = []

        props = self.manager.get_server_properties(self._pending_server)
        for key in sorted(props, key=lambda k: 0 if k in PROPERTY_GUIDE else 1):
            self._add_row(key, props[key])
        self._reflow("")

        self.properties_scroll.show()
        self.loading_lbl.hide()
        self.btn_save.setEnabled(True)
        self.search_bar.setEnabled(True)

    def _add_row(self, key, value):
        row = QFrame(self.container)
        row.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; border-radius: 10px; border: 1px solid {COLOR_BORDER};"
        )
        row.setFixedSize(345, 175)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(15, 14, 15, 14)
        rl.setSpacing(8)

        meta = PROPERTY_GUIDE.get(key, {"desc_key": "", "type": "text"})
        t = meta["type"]
        desc_text = _t(meta["desc_key"]) if meta.get("desc_key") else key

        hl = QHBoxLayout()
        hl.setSpacing(12)
        is_known = key in PROPERTY_GUIDE
        lbl_key = QLabel(key, row)
        key_color = COLOR_ACCENT if is_known else "#e4e4e7"
        lbl_key.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {key_color}; background: transparent; border: none;")
        lbl_desc = QLabel(desc_text, row)
        lbl_desc.setStyleSheet(f"font-size: 11px; color: {COLOR_TEXT_SEC}; background: transparent; border: none;")
        lbl_desc.setWordWrap(True)

        if t == "bool":
            widget = QCheckBox(_t("PROPS_BOOL_ENABLED"), row)
            widget.setChecked(value.lower() == "true")
            widget.setStyleSheet(
                "QCheckBox { color: #e4e4e7; }"
                "QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #3f3f46; background: #18181b; }"
                f"QCheckBox::indicator:checked {{ background: {COLOR_ACCENT}; border: 1px solid {COLOR_ACCENT}; }}"
                "QCheckBox::indicator:hover { border: 1px solid #737373; }"
            )
        elif t == "int":
            widget = QSpinBox(row)
            widget.setRange(meta.get("min", 0), meta.get("max", 999999))
            try:
                widget.setValue(int(value))
            except (ValueError, TypeError):
                pass
            widget.setStyleSheet("QSpinBox { background-color: #17191f; border: 1px solid #3f3f46; border-radius: 8px; padding: 6px 10px; } QSpinBox:hover { border: 1px solid #6b7280; }")
            disable_wheel_value_change(widget)
        elif t == "combo":
            widget = QComboBox(row)
            widget.addItems(meta["options"])
            widget.setCurrentText(value)
            widget.setStyleSheet("QComboBox { background-color: #17191f; border: 1px solid #3f3f46; border-radius: 8px; padding: 6px 10px; } QComboBox:hover { border: 1px solid #6b7280; }")
            disable_wheel_value_change(widget)
        else:
            widget = QLineEdit(row)
            widget.setText(value)
            widget.setStyleSheet("QLineEdit { background-color: #17191f; border: 1px solid #3f3f46; border-radius: 8px; padding: 8px 10px; } QLineEdit:hover { border: 1px solid #6b7280; }")

        self.widgets_map[key] = (widget, row, desc_text)
        self.card_order.append(key)
        hl.addWidget(lbl_key)
        hl.addWidget(widget, 1)
        rl.addLayout(hl)
        rl.addWidget(lbl_desc)

    def _filter(self, text):
        self._reflow(text)

    def _reflow(self, text):
        text = text.lower().strip()
        visible = []
        for key in self.card_order:
            _, row, desc = self.widgets_map[key]
            self.form.removeWidget(row)
            match = (not text) or (text in key.lower()) or (text in desc.lower())
            row.setVisible(match)
            if match:
                visible.append(key)
        for idx, key in enumerate(visible):
            _, row, _ = self.widgets_map[key]
            self.form.addWidget(row, idx // 3, idx % 3)

    def save_all(self):
        new_props = {}
        for key, (w, _row, _desc) in self.widgets_map.items():
            t = PROPERTY_GUIDE.get(key, {"type": "text"})["type"]
            if t == "bool":
                val = "true" if w.isChecked() else "false"
            elif t == "int":
                val = str(w.value())
            elif t == "combo":
                val = w.currentText()
            else:
                val = w.text()
            new_props[key] = val
        try:
            self.manager.save_server_properties(self.current_server, new_props)
            self.main.show_toast(_t("PROPS_MSG_SAVED"), False)
        except OSError as exc:
            self.main.show_toast(_t("PROPS_MSG_SAVE_ERR", error=exc), True)

    def go_back(self):
        self.main.show_dashboard(self.current_server)
