from collections import deque
import traceback

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPropertyAnimation,
    QRunnable, Qt, Signal, Slot,
)
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFont, QLinearGradient,
    QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QGraphicsOpacityEffect,
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from styles import (
    COLOR_ACCENT, COLOR_BG_CARD, COLOR_DANGER, COLOR_OFFLINE,
    COLOR_TEXT_MAIN, COLOR_TEXT_SEC, COLOR_WARN, FONT_FAMILY,
)
from translations import _t


class HistoryChart(QWidget):
    def __init__(self, color_hex=COLOR_ACCENT):
        super().__init__()
        self.setFixedHeight(30)
        self.default_color = QColor(color_hex)
        self.current_color = self.default_color
        self.data = deque([0] * 50, maxlen=50)
        self.max_val = 100.0

    def add_value(self, val, max_v, warn=False):
        self.max_val = max_v if max_v > 0 else 100.0
        self.data.append(min(val, self.max_val))
        self.current_color = QColor(COLOR_WARN) if warn else self.default_color
        self.update()

    def clear_data(self):
        self.data = deque([0] * 50, maxlen=50)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.Antialiasing)
        try:
            w, h = self.width(), self.height()
            points = list(self.data)
            if not points:
                return
            step_x = w / (len(points) - 1) if len(points) > 1 else 0

            path = QPainterPath()
            path.moveTo(0, h)
            for i, val in enumerate(points):
                y = max(0, min(h, h - (val / self.max_val) * h))
                path.lineTo(0, y) if i == 0 else path.lineTo(i * step_x, y)
            path.lineTo(w, h)
            path.lineTo(0, h)

            grad = QLinearGradient(0, 0, 0, h)
            c_top = QColor(self.current_color)
            c_top.setAlpha(100)
            c_bot = QColor(self.current_color)
            c_bot.setAlpha(0)
            grad.setColorAt(0, c_top)
            grad.setColorAt(1, c_bot)
            painter.fillPath(path, QBrush(grad))

            stroke = QPainterPath()
            for i, val in enumerate(points):
                y = max(0, min(h, h - (val / self.max_val) * h))
                stroke.moveTo(0, y) if i == 0 else stroke.lineTo(i * step_x, y)
            painter.setPen(QPen(self.current_color, 2))
            painter.drawPath(stroke)
        finally:
            painter.end()


class ServerListItem(QFrame):
    def __init__(self, name, core_info, is_running, callback):
        super().__init__()
        self.server_name = name
        self.callback = callback
        self.setFixedHeight(60)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QFrame { background-color: transparent; border-radius: 8px; } QFrame:hover { background-color: #1f1f22; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background-color: {COLOR_ACCENT if is_running else '#3f3f46'}; border-radius: 4px;")
        layout.addWidget(dot)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignVCenter)
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {COLOR_TEXT_MAIN}; background: transparent;")
        lbl_meta = QLabel(core_info)
        lbl_meta.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {COLOR_TEXT_SEC}; background: transparent;")
        text_layout.addWidget(lbl_name)
        text_layout.addWidget(lbl_meta)
        layout.addLayout(text_layout)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.callback(self.server_name)


class StatusBadge(QLabel):
    def __init__(self, state="OFFLINE"):
        super().__init__("")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(120, 32)
        self.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))
        self.update_state(state)

    def update_state(self, state):
        if state == "ONLINE":
            text, color, bg = _t("STATUS_ONLINE"), "#10b981", "rgba(16, 185, 129, 0.15)"
        elif state == "STARTING":
            text, color, bg = _t("STATUS_STARTING"), "#f59e0b", "rgba(245, 158, 11, 0.15)"
        elif state == "STOPPING":
            text, color, bg = _t("STATUS_STOPPING"), "#f97316", "rgba(249, 115, 22, 0.15)"
        else:
            text, color, bg = _t("STATUS_OFFLINE"), "#71717a", "#27272a"
        self.setText(text)
        self.setStyleSheet(f"background-color: {bg}; color: {color}; border-radius: 8px;")


class ModernButton(QPushButton):
    def __init__(self, text, bg_color=COLOR_BG_CARD, text_color="#FFF",
                 hover_color="#27272a", is_accent=False, is_danger=False):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(45)
        if is_accent:
            style_bg, style_border, style_hover = "#18181b", f"1px solid {COLOR_ACCENT}", "#1f332a"
            fw = "bold"
        elif is_danger:
            style_bg, style_border, style_hover = "#18181b", f"1px solid {COLOR_DANGER}", "#331f1f"
            fw = "bold"
        else:
            style_bg, style_border, style_hover = bg_color, "none", hover_color
            fw = "600"
        self.setStyleSheet(f"""
            QPushButton {{ background-color: {style_bg}; color: {text_color}; border-radius: 8px;
                border: {style_border}; font-weight: {fw}; font-size: 14px; padding: 0 25px; text-align: center; }}
            QPushButton:hover {{ background-color: {style_hover}; border: {style_border}; }}
            QPushButton:pressed {{ background-color: {style_hover}; margin-top: 1px; }}
            QPushButton:disabled {{ background-color: #18181b; color: #52525b; border: 1px solid #27272a; }}
        """)
        self.shadow = None
        if is_accent or is_danger:
            self.shadow = QGraphicsDropShadowEffect()
            self.shadow.setBlurRadius(15)
            c = QColor(COLOR_ACCENT if is_accent else COLOR_DANGER)
            c.setAlpha(60)
            self.shadow.setColor(c)
            self.shadow.setOffset(0, 4)
            self.setGraphicsEffect(self.shadow)

    def set_glow_color(self, color_hex):
        if not self.shadow:
            return
        c = QColor(color_hex)
        c.setAlpha(80)
        self.shadow.setColor(c)

    def changeEvent(self, event):
        if event.type() == QEvent.EnabledChange and self.shadow:
            self.shadow.setEnabled(self.isEnabled())
        super().changeEvent(event)


class FilterButton(ModernButton):
    def __init__(self, text, active_color=COLOR_ACCENT):
        QPushButton.__init__(self, text)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(30)
        self.setMinimumWidth(80)
        self.active_color = active_color
        self.is_active = True
        self.update_style()

    def toggle(self):
        self.is_active = not self.is_active
        self.update_style()
        return self.is_active

    def update_style(self):
        c = QColor(self.active_color)
        rgba_bg = f"rgba({c.red()}, {c.green()}, {c.blue()}, 0.15)"
        rgba_hov = f"rgba({c.red()}, {c.green()}, {c.blue()}, 0.25)"
        if self.is_active:
            self.setStyleSheet(f"""
                QPushButton {{ background-color: {rgba_bg}; color: {self.active_color};
                    border: 1px solid {self.active_color}; border-radius: 6px; font-weight: bold; font-size: 12px; }}
                QPushButton:hover {{ background-color: {rgba_hov}; }}
            """)
        else:
            self.setStyleSheet("""
                QPushButton { background-color: #18181b; color: #52525b; border: 1px solid #27272a;
                    border-radius: 6px; font-weight: 600; font-size: 12px; }
                QPushButton:hover { background-color: #27272a; color: #a1a1aa; }
            """)


class MetricCard(QFrame):
    def __init__(self, title, icon, suffix="", color=COLOR_ACCENT, minimal=False):
        super().__init__()
        self.setFixedSize(155, 155)
        self.setStyleSheet(f"QFrame {{ background-color: {COLOR_BG_CARD}; border-radius: 16px; }}")
        self.suffix = suffix
        self.minimal = minimal
        self.base_color = color

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(5)

        h = QHBoxLayout()
        self.title_lbl = QLabel(f"{icon}  {title}")
        self.title_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 700; background: transparent;")
        h.addWidget(self.title_lbl)
        h.addStretch()
        layout.addLayout(h)

        self.value_lbl = QLabel(f"0{suffix}")
        self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: white; background: transparent;")
        layout.addWidget(self.value_lbl)
        layout.addStretch()

        self.chart = None if minimal else HistoryChart(color)
        if self.chart:
            layout.addWidget(self.chart)

    def set_offline(self):
        self.setStyleSheet(f"QFrame {{ background-color: {COLOR_OFFLINE}; border-radius: 16px; }}")
        self.title_lbl.setStyleSheet("color: #52525b; font-size: 11px; font-weight: 700; background: transparent;")
        self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #52525b; background: transparent;")
        self.value_lbl.setText(_t("METRIC_OFFLINE"))
        if self.chart:
            self.chart.hide()

    def set_online(self):
        self.setStyleSheet(f"QFrame {{ background-color: {COLOR_BG_CARD}; border-radius: 16px; }}")
        self.title_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 700; background: transparent;")
        self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: white; background: transparent;")
        if self.chart:
            self.chart.show()

    def update_data(self, value, max_val, text_override=None):
        if value == -1.0:
            self.set_offline()
            if self.chart:
                self.chart.clear_data()
            return
        self.set_online()
        is_overflow = (value > max_val) and (max_val > 0)
        if self.chart:
            self.chart.add_value(value, max_val, warn=is_overflow)
        if text_override:
            self.value_lbl.setText(text_override)
            color = "#f59e0b" if is_overflow else "white"
            self.value_lbl.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {color}; background: transparent;")
        else:
            self.value_lbl.setText(f"{value:.1f}{self.suffix}")
            self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: white; background: transparent;")


class ToastNotification(QFrame):
    def __init__(self, parent, message, is_error=False):
        super().__init__(parent)
        color = COLOR_DANGER if is_error else COLOR_ACCENT
        bg = "#2c1515" if is_error else "#062b1e"
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-radius: 8px; border: 1px solid {color}; }}"
            f"QLabel {{ border: none; background: transparent; color: {color}; font-weight: bold; font-size: 14px; }}"
        )
        self.setFixedSize(320, 50)
        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignCenter)
        layout = QHBoxLayout(self)
        layout.addWidget(lbl)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)

        pw = parent.width()
        self.move((pw - 320) // 2, -60)
        self.show()

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setStartValue(QPoint((pw - 320) // 2, -60))
        self.anim.setEndValue(QPoint((pw - 320) // 2, 30))
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        self.anim.start()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, self._close)

    def _close(self):
        self.anim_out = QPropertyAnimation(self, b"pos")
        self.anim_out.setDuration(300)
        self.anim_out.setStartValue(self.pos())
        self.anim_out.setEndValue(QPoint(self.pos().x(), -70))
        self.anim_out.setEasingCurve(QEasingCurve.InBack)
        self.anim_out.finished.connect(self.deleteLater)
        self.anim_out.start()


class ServerBridge(QObject):
    log_signal = Signal(str, str)
    stats_signal = Signal(float, float, float, str, int, float)  # ram, tps, disk, uptime, players, cpu
    state_signal = Signal(str)
    stop_signal = Signal(int)
    tunnel_signal = Signal(str, str)

    def on_log(self, text, type_): self.log_signal.emit(text, type_)
    def on_stats(self, ram, tps, disk, uptime, players, cpu): self.stats_signal.emit(ram, tps, disk, uptime, players, cpu)
    def on_state(self, state): self.state_signal.emit(state)
    def on_stop(self, code): self.stop_signal.emit(code)
    def on_tunnel_output(self, line, pub_ip): self.tunnel_signal.emit(line, pub_ip or "")


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class WorkerTask(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.function()
        except Exception as error:
            self.signals.error.emit(f"{error}\n{traceback.format_exc()}")
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()
