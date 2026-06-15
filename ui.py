import sys
import os
import threading
import re
import core
import datetime
from collections import deque
from translations import _t, Translator
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QListWidget, QListWidgetItem, QLabel, QPushButton, QStackedWidget,
    QFrame, QProgressBar, QPlainTextEdit, QLineEdit, QFileDialog,
    QMessageBox, QSlider, QScrollArea, QGraphicsDropShadowEffect, 
    QCheckBox, QComboBox, QSizePolicy, QGridLayout, QSplitter, QSpinBox,
    QGraphicsOpacityEffect
)
from PySide6.QtCore import (
    Qt, QSize, Signal, QObject, Slot, QTimer, QPropertyAnimation, 
    QEasingCurve, QPoint, QParallelAnimationGroup, QSequentialAnimationGroup, QEvent, QUrl,
    QRunnable, QThreadPool
)
from PySide6.QtGui import (
    QFont, QColor, QCursor, QIcon, QPainter, QLinearGradient, QBrush, 
    QPen, QPainterPath, QDesktopServices, QClipboard
) 

# --- COLOR PALETTE ---
COLOR_BG_MAIN = "#09090b"       
COLOR_BG_SIDEBAR = "#121214"    
COLOR_BG_CARD = "#18181b"       
COLOR_ACCENT = "#10b981"        
COLOR_ACCENT_HOVER = "#059669"
COLOR_DANGER = "#ef4444"        
COLOR_DANGER_HOVER = "#dc2626"
COLOR_WARN = "#f59e0b"          
COLOR_TEXT_MAIN = "#fafafa"     
COLOR_TEXT_SEC = "#a1a1aa"      
COLOR_BORDER = "#27272a"
COLOR_OFFLINE = "#27272a" 

FONT_FAMILY = "Segoe UI"

# --- PROPERTY GUIDE (KNOWLEDGE BASE) ---
PROPERTY_GUIDE = {
    "gamemode": {"desc_key": "PROP_DESC_GAMEMODE", "type": "combo", "options": ["survival", "creative", "adventure", "spectator"]},
    "difficulty": {"desc_key": "PROP_DESC_DIFFICULTY", "type": "combo", "options": ["peaceful", "easy", "normal", "hard"]},
    "motd": {"desc_key": "PROP_DESC_MOTD", "type": "text"},
    "max-players": {"desc_key": "PROP_DESC_MAX_PLAYERS", "type": "int", "min": 1, "max": 10000},
    "server-port": {"desc_key": "PROP_DESC_SERVER_PORT", "type": "int", "min": 1024, "max": 65535},
    "pvp": {"desc_key": "PROP_DESC_PVP", "type": "bool"},
    "online-mode": {"desc_key": "PROP_DESC_ONLINE_MODE", "type": "bool"},
    "allow-flight": {"desc_key": "PROP_DESC_ALLOW_FLIGHT", "type": "bool"},
    "white-list": {"desc_key": "PROP_DESC_WHITE_LIST", "type": "bool"},
    "view-distance": {"desc_key": "PROP_DESC_VIEW_DISTANCE", "type": "int", "min": 2, "max": 32},
    "simulation-distance": {"desc_key": "PROP_DESC_SIM_DISTANCE", "type": "int", "min": 2, "max": 32},
    "level-seed": {"desc_key": "PROP_DESC_LEVEL_SEED", "type": "text"},
    "hardcore": {"desc_key": "PROP_DESC_HARDCORE", "type": "bool"},
    "spawn-protection": {"desc_key": "PROP_DESC_SPAWN_PROTECTION", "type": "int", "min": 0},
    "enable-command-block": {"desc_key": "PROP_DESC_COMMAND_BLOCK", "type": "bool"},
    "spawn-monsters": {"desc_key": "PROP_DESC_SPAWN_MONSTERS", "type": "bool"},
    "spawn-animals": {"desc_key": "PROP_DESC_SPAWN_ANIMALS", "type": "bool"},
    "spawn-npcs": {"desc_key": "PROP_DESC_SPAWN_NPCS", "type": "bool"},
    "allow-nether": {"desc_key": "PROP_DESC_ALLOW_NETHER", "type": "bool"},
    "level-type": {"desc_key": "PROP_DESC_LEVEL_TYPE", "type": "text"},
    "generate-structures": {"desc_key": "PROP_DESC_GEN_STRUCT", "type": "bool"},
    "max-build-height": {"desc_key": "PROP_DESC_MAX_BUILD_HEIGHT", "type": "int", "min": 64, "max": 1024},
    "rate-limit": {"desc_key": "PROP_DESC_RATE_LIMIT", "type": "int", "min": 0},
    "resource-pack": {"desc_key": "PROP_DESC_RESOURCE_PACK", "type": "text"},
    "enforce-whitelist": {"desc_key": "PROP_DESC_ENFORCE_WHITELIST", "type": "bool"},
    "entity-broadcast-range-percentage": {"desc_key": "PROP_DESC_ENTITY_BROADCAST", "type": "int", "min": 10, "max": 1000},
    "enable-query": {"desc_key": "PROP_DESC_ENABLE_QUERY", "type": "bool"},
    "enable-rcon": {"desc_key": "PROP_DESC_ENABLE_RCON", "type": "bool"},
    "sync-chunk-writes": {"desc_key": "PROP_DESC_SYNC_CHUNK_WRITES", "type": "bool"},
    "network-compression-threshold": {"desc_key": "PROP_DESC_NET_COMPRESS", "type": "int", "min": -1},
    "prevent-proxy-connections": {"desc_key": "PROP_DESC_PREVENT_PROXY", "type": "bool"}
}

# --- GLOBAL STYLES ---
STYLESHEET = f"""
QMainWindow {{ background-color: {COLOR_BG_MAIN}; }}
QWidget {{ font-family: '{FONT_FAMILY}', sans-serif; color: {COLOR_TEXT_MAIN}; }}

/* LIST WIDGET */
QListWidget {{ 
    background-color: transparent; 
    border: none; 
    outline: none; 
    padding: 10px; 
}}
QListWidget::item {{ 
    height: 60px; 
    padding-left: 0px; 
    border-radius: 8px; 
    margin-bottom: 5px; 
    color: {COLOR_TEXT_SEC}; 
    font-size: 14px; 
    font-weight: 600; 
    border: none; 
}}
QListWidget::item:selected {{ 
    background-color: #27272a; 
    color: {COLOR_ACCENT}; 
    border-left: 4px solid {COLOR_ACCENT}; 
}}
QListWidget::item:hover {{ 
    background-color: #1f1f22; 
    color: {COLOR_TEXT_MAIN}; 
}}

/* SCROLLBAR */
QScrollBar:vertical {{ 
    border: none; 
    background: {COLOR_BG_MAIN}; 
    width: 6px; 
    margin: 0px; 
}}
QScrollBar::handle:vertical {{ 
    background: #3f3f46; 
    min-height: 20px; 
    border-radius: 3px; 
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

/* CONSOLE */
QPlainTextEdit {{ 
    background-color: #0c0c0e; 
    border: none; 
    border-radius: 8px; 
    font-family: 'Consolas', monospace; 
    font-size: 13px; 
    color: #e4e4e7; 
    padding: 15px; 
    selection-background-color: #3f3f46; 
}}

/* INPUTS */
QLineEdit {{ 
    background-color: #121214; 
    border: 1px solid transparent; 
    border-radius: 6px; 
    padding: 10px 12px; 
    color: white; 
    font-size: 13px; 
}}
QLineEdit:focus {{ 
    border: 1px solid {COLOR_ACCENT}; 
    background-color: #18181b; 
}}
QLineEdit:hover {{
    border: 1px solid #3f3f46;
}}
QLineEdit:disabled {{
    color: #52525b;
    background-color: #09090b;
}}

QSpinBox {{ 
    background-color: #121214; 
    border: 1px solid transparent; 
    border-radius: 6px; 
    padding: 5px; 
    color: white; 
    font-size: 13px; 
}}
QSpinBox:focus {{ border: 1px solid {COLOR_ACCENT}; }}

/* SLIDERS */
QSlider {{ min-height: 26px; background: transparent; }}
QSlider::groove:horizontal {{ 
    border: none; 
    height: 6px; 
    background: #27272a; 
    margin: 0px; 
    border-radius: 3px; 
}}
QSlider::handle:horizontal {{ 
    background: {COLOR_ACCENT}; 
    border: none; 
    width: 16px; 
    height: 16px; 
    margin: -5px 0; 
    border-radius: 8px; 
}}
QSlider::sub-page:horizontal {{ background: {COLOR_ACCENT}; border-radius: 3px; }}

/* COMBO & CHECKBOX */
QComboBox {{ 
    background-color: #1c1c1f; 
    border: none; 
    border-radius: 6px; 
    padding: 5px 10px; 
    color: white; 
}}
QCheckBox {{ color: {COLOR_TEXT_SEC}; spacing: 8px; }}
QCheckBox::indicator {{ 
    width: 18px; 
    height: 18px; 
    border-radius: 4px; 
    background: #1c1c1f; 
    border: none; 
}}
QCheckBox::indicator:checked {{ background-color: {COLOR_ACCENT}; }}
QCheckBox::indicator:hover {{
    border: 1px solid #52525b;
}}

QFrame {{ border: none; }}
QLabel {{ border: none; }}
"""

# --- UTILS ---

def fade_in(widget, duration=200):
    # Використовуємо прозорість замість руху, щоб інтерфейс не "з'їжджав"
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    
    # Зберігаємо посилання на анімацію у віджеті, щоб Python не видалив її завчасно (GC fix)
    widget.fade_anim = QPropertyAnimation(effect, b"opacity")
    widget.fade_anim.setStartValue(0)
    widget.fade_anim.setEndValue(1)
    widget.fade_anim.setDuration(duration)
    widget.fade_anim.setEasingCurve(QEasingCurve.OutQuad)
    
    # CLEANUP: Видаляємо ефект після завершення, щоб відновити нормальне малювання (фікс багів QPainter)
    def cleanup():
        widget.setGraphicsEffect(None)
    widget.fade_anim.finished.connect(cleanup)
    
    widget.fade_anim.start()

def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def copy_to_clipboard(text):
    cb = QApplication.clipboard()
    cb.setText(text) # Простий метод без зайвих параметрів, щоб уникнути помилок

def disable_wheel_value_change(widget):
    # Prevent value hijacking and let wheel scroll bubble up to parent QScrollArea.
    widget.wheelEvent = lambda event: event.ignore()

# --- CUSTOM WIDGETS ---

class HistoryChart(QWidget):
    def __init__(self, color_hex=COLOR_ACCENT):
        super().__init__()
        self.setFixedHeight(30) # Зменшено для компактності
        self.default_color = QColor(color_hex)
        self.current_color = self.default_color
        self.data = deque([0]*50, maxlen=50)
        self.max_val = 100.0

    def add_value(self, val, max_v, warn=False):
        self.max_val = max_v if max_v > 0 else 100.0
        visual_val = min(val, self.max_val)
        self.data.append(visual_val)
        self.current_color = QColor(COLOR_WARN) if warn else self.default_color
        self.update()

    def clear_data(self):
        self.data = deque([0]*50, maxlen=50)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        # Safety check: if painter failed to init (e.g. effect conflict), stop here
        if not painter.isActive():
            return

        painter.setRenderHint(QPainter.Antialiasing)
        
        try:
            w = self.width()
            h = self.height()
            
            path = QPainterPath()
            path.moveTo(0, h)
            
            points = list(self.data)
            if not points:
                return

            step_x = w / (len(points) - 1) if len(points) > 1 else 0
            
            for i, val in enumerate(points):
                ratio = val / self.max_val
                y = h - (ratio * h)
                y = max(0, min(h, y))
                if i == 0:
                    path.lineTo(0, y)
                else:
                    path.lineTo(i * step_x, y)
                    
            path.lineTo(w, h)
            path.lineTo(0, h)
            
            grad = QLinearGradient(0, 0, 0, h)
            c_top = QColor(self.current_color)
            c_top.setAlpha(100)
            c_bottom = QColor(self.current_color)
            c_bottom.setAlpha(0)
            grad.setColorAt(0, c_top)
            grad.setColorAt(1, c_bottom)
            
            painter.fillPath(path, QBrush(grad))
            
            stroke_path = QPainterPath()
            for i, val in enumerate(points):
                ratio = val / self.max_val
                y = h - (ratio * h)
                y = max(0, min(h, y))
                if i == 0:
                    stroke_path.moveTo(0, y)
                else:
                    stroke_path.lineTo(i * step_x, y)
            
            pen = QPen(self.current_color, 2)
            painter.setPen(pen)
            painter.drawPath(stroke_path)
        finally:
            painter.end()

class ServerListItem(QFrame):
    def __init__(self, name, core_info, is_running, callback):
        super().__init__()
        self.server_name = name
        self.callback = callback
        self.setFixedHeight(60)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{ background-color: transparent; border-radius: 8px; }}
            QFrame:hover {{ background-color: #1f1f22; }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)
        
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(8, 8)
        color = COLOR_ACCENT if is_running else "#3f3f46"
        self.status_dot.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        layout.addWidget(self.status_dot)
        
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignVCenter)
        
        lbl_name = QLabel(name)
        lbl_name.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {COLOR_TEXT_MAIN}; background: transparent;")
        text_layout.addWidget(lbl_name)
        
        lbl_meta = QLabel(core_info)
        lbl_meta.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {COLOR_TEXT_SEC}; background: transparent;")
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
        self.update_state(state)
        self.setFont(QFont(FONT_FAMILY, 11, QFont.Bold))

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
    def __init__(self, text, bg_color=COLOR_BG_CARD, text_color="#FFF", hover_color="#27272a", is_accent=False, is_danger=False):
        super().__init__(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(45)
        
        font_weight = "600"
        
        style_bg = bg_color
        style_border = "none"
        style_hover = hover_color
        
        if is_accent:
            font_weight = "bold"
            style_bg = "#18181b" 
            style_border = f"1px solid {COLOR_ACCENT}"
            style_hover = "#1f332a" 
        elif is_danger:
            font_weight = "bold"
            style_bg = "#18181b"
            style_border = f"1px solid {COLOR_DANGER}"
            style_hover = "#331f1f" 

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {style_bg};
                color: {text_color};
                border-radius: 8px;
                border: {style_border};
                font-weight: {font_weight};
                font-size: 14px;
                padding: 0 25px;
                text-align: center;
            }}
            QPushButton:hover {{
                background-color: {style_hover};
                border: {style_border};
            }}
            QPushButton:pressed {{
                background-color: {style_hover};
                margin-top: 1px;
            }}
            QPushButton:disabled {{
                background-color: #18181b;
                color: #52525b;
                border: 1px solid #27272a;
            }}
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
        if event.type() == QEvent.EnabledChange:
            if self.shadow:
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
        rgba_hover = f"rgba({c.red()}, {c.green()}, {c.blue()}, 0.25)"

        if self.is_active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {rgba_bg}; 
                    color: {self.active_color}; 
                    border: 1px solid {self.active_color};
                    border-radius: 6px; font-weight: bold; font-size: 12px;
                }}
                QPushButton:hover {{ background-color: {rgba_hover}; }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: #18181b; color: #52525b; border: 1px solid #27272a;
                    border-radius: 6px; font-weight: 600; font-size: 12px;
                }}
                QPushButton:hover {{ background-color: #27272a; color: #a1a1aa; }}
            """)

class MetricCard(QFrame):
    def __init__(self, title, icon, suffix="", color=COLOR_ACCENT, minimal=False):
        super().__init__()
        # FIXED SIZE: Квадратні картки, які не змінюють розмір
        self.setFixedSize(155, 155)
        self.setStyleSheet(f"QFrame {{ background-color: {COLOR_BG_CARD}; border-radius: 16px; }}")
        self.suffix = suffix
        self.minimal = minimal
        self.base_color = color
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(5)
        
        h_layout = QHBoxLayout()
        self.title_lbl = QLabel(f"{icon}  {title}")
        self.title_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 700; background: transparent; text-transform: uppercase;")
        h_layout.addWidget(self.title_lbl)
        h_layout.addStretch()
        layout.addLayout(h_layout)
        
        self.value_lbl = QLabel(f"0{suffix}")
        self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: white; background: transparent;")
        layout.addWidget(self.value_lbl)
        
        layout.addStretch()
        
        if not minimal:
            self.chart = HistoryChart(color)
            layout.addWidget(self.chart)
        else:
            self.chart = None
    
    def set_offline(self):
        self.setStyleSheet(f"QFrame {{ background-color: {COLOR_OFFLINE}; border-radius: 16px; }}")
        self.title_lbl.setStyleSheet(f"color: #52525b; font-size: 11px; font-weight: 700; background: transparent;")
        self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: #52525b; background: transparent;")
        self.value_lbl.setText(_t("METRIC_OFFLINE"))
        if self.chart: self.chart.hide()

    def set_online(self):
        self.setStyleSheet(f"QFrame {{ background-color: {COLOR_BG_CARD}; border-radius: 16px; }}")
        self.title_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 700; background: transparent;")
        self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: white; background: transparent;")
        if self.chart: self.chart.show()

    def update_data(self, value, max_val, text_override=None):
        if value == -1.0:
            self.set_offline()
            if self.chart: self.chart.clear_data()
            return

        self.set_online()
        is_overflow = (value > max_val) and (max_val > 0)
        if self.chart: self.chart.add_value(value, max_val, warn=is_overflow)
        
        if text_override: 
            self.value_lbl.setText(text_override)
            if is_overflow: self.value_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #f59e0b; background: transparent;")
            else: self.value_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: white; background: transparent;")
        else: self.value_lbl.setText(f"{value:.1f}{self.suffix}")
        # Reset large font if no override
        if not text_override:
             self.value_lbl.setStyleSheet("font-size: 20px; font-weight: 800; color: white; background: transparent;")

class ServerBridge(QObject):
    log_signal = Signal(str, str)
    stats_signal = Signal(float, float, float, str, int, float, float, float)
    state_signal = Signal(str)
    stop_signal = Signal(int)
    playit_signal = Signal(str, str) # line, public_ip

    def on_log(self, text, type_): self.log_signal.emit(text, type_)
    def on_stats(self, ram, tps, disk, uptime, players, cpu, gc, tick): self.stats_signal.emit(ram, tps, disk, uptime, players, cpu, gc, tick)
    def on_state(self, state): self.state_signal.emit(state)
    def on_stop(self, code): self.stop_signal.emit(code)
    def on_playit_output(self, line, pub_ip): self.playit_signal.emit(line, pub_ip or "")


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
            self.signals.error.emit(str(error))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class ToastNotification(QFrame):
    def __init__(self, parent, message, is_error=False):
        super().__init__(parent)
        color = COLOR_DANGER if is_error else COLOR_ACCENT
        bg = "#2c1515" if is_error else "#062b1e"
        self.setStyleSheet(f"QFrame {{ background-color: {bg}; border-radius: 8px; border: 1px solid {color}; }} QLabel {{ border: none; background: transparent; color: {color}; font-weight: bold; font-size: 14px; }}")
        self.setFixedSize(320, 50)
        layout = QHBoxLayout(self)
        lbl = QLabel(message)
        lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0,0,0,100))
        shadow.setOffset(0, 8)
        self.setGraphicsEffect(shadow)
        
        self.parent_width = parent.width()
        self.start_y = -60
        self.target_y = 30
        self.move((self.parent_width - 320) // 2, self.start_y)
        self.show()
        
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setStartValue(QPoint((self.parent_width - 320) // 2, self.start_y))
        self.anim.setEndValue(QPoint((self.parent_width - 320) // 2, self.target_y))
        self.anim.setEasingCurve(QEasingCurve.OutBack)
        self.anim.start()
        
        QTimer.singleShot(3000, self.close_toast)

    def close_toast(self):
        self.anim_out = QPropertyAnimation(self, b"pos")
        self.anim_out.setDuration(300)
        self.anim_out.setStartValue(self.pos())
        self.anim_out.setEndValue(QPoint(self.pos().x(), -70))
        self.anim_out.setEasingCurve(QEasingCurve.InBack)
        self.anim_out.finished.connect(self.deleteLater)
        self.anim_out.start()

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
        self.log_history = [] 
        self.filter_info = True
        self.filter_warn = True
        self.filter_error = True
        
        self.setup_ui()
        self.connect_bridge()

    def setup_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)
        left_col = QVBoxLayout()
        left_col.setSpacing(20)
        
        # Header
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

        # Console
        console_wrapper = QFrame()
        console_wrapper.setStyleSheet(f"background-color: #0c0c0e; border-radius: 12px;")
        cw_layout = QVBoxLayout(console_wrapper)
        cw_layout.setContentsMargins(0,0,0,0)
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
        
        line = QFrame()
        line.setFixedWidth(1)
        line.setFixedHeight(20)
        line.setStyleSheet("background: #27272a;")
        th_layout.addWidget(line)
        
        btn_save_log = ModernButton(_t("DASH_BTN_SAVE_LOG"), bg_color="transparent", hover_color="#27272a")
        btn_save_log.setMinimumWidth(132)
        btn_save_log.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_save_log.setFixedHeight(30)
        btn_save_log.clicked.connect(self.save_log)
        btn_save_log.setToolTip(_t("DASH_TIP_SAVE_LOG"))
        
        btn_clear_log = ModernButton(_t("DASH_BTN_CLEAR_LOG"), bg_color="transparent", hover_color="#27272a")
        btn_clear_log.setMinimumWidth(132)
        btn_clear_log.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        btn_clear_log.setFixedHeight(30)
        btn_clear_log.clicked.connect(self.clear_console)
        btn_clear_log.setToolTip(_t("DASH_TIP_CLEAR_LOG"))
        
        th_layout.addWidget(btn_save_log)
        th_layout.addWidget(btn_clear_log)
        
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

        # Right Column
        right_col = QVBoxLayout()
        right_col.setSpacing(15)
        
        lbl_acts = QLabel(_t("DASH_SECTION_CONTROL"))
        lbl_acts.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-weight: bold; font-size: 12px; letter-spacing: 1px;")
        right_col.addWidget(lbl_acts)
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
        
        lbl_stats = QLabel(_t("DASH_SECTION_MONITOR"))
        lbl_stats.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-weight: bold; font-size: 12px; letter-spacing: 1px;")
        right_col.addWidget(lbl_stats)
        
        # Scroll Area for Stats
        scroll_stats = QScrollArea()
        scroll_stats.setWidgetResizable(True)
        scroll_stats.setStyleSheet("background: transparent; border: none;")
        scroll_stats.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        scroll_stats.setMinimumWidth(340) # Ensure content fits 2 columns of 155px
        
        stats_container = QWidget()
        stats_grid = QGridLayout(stats_container)
        stats_grid.setSpacing(12)
        stats_grid.setContentsMargins(0,0,0,0)
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

    def connect_bridge(self):
        self.bridge.log_signal.connect(self.on_log)
        self.bridge.stats_signal.connect(lambda ram, tps, disk, uptime, players, cpu, _gc, _mspt: self.on_stats(ram, tps, disk, uptime, players, cpu))
        self.bridge.state_signal.connect(self.on_state_change)
        self.bridge.stop_signal.connect(self.on_process_stop)

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
        display_limit = 2000
        start_idx = max(0, len(self.log_history) - display_limit)
        
        for text, type_ in self.log_history[start_idx:]:
            if self.should_show_log(type_):
                self.append_log_to_widget(text, type_)
        
        # Always scroll to bottom on refresh
        sb = self.console_out.verticalScrollBar()
        sb.setValue(sb.maximum())

    def should_show_log(self, type_):
        if type_ == "INFO" and not self.filter_info: return False
        if type_ == "WARN" and not self.filter_warn: return False
        if type_ == "ERROR" and not self.filter_error: return False
        return True

    def append_log_to_widget(self, text, type_):
        color = "#e4e4e7"
        if type_ == "WARN": color = "#fbbf24"
        elif type_ == "ERROR": color = "#ef4444"
        self.console_out.appendHtml(f'<span style="color:{color};">{text}</span>')

    def clear_console(self):
        self.console_out.clear()
        self.log_history = []

    def save_log(self):
        if not self.log_history:
            self.main.show_toast(_t("DASH_MSG_LOG_EMPTY"), True)
            return
            
        fname, _ = QFileDialog.getSaveFileName(self, _t("DASH_TIP_SAVE_LOG"), f"server_log_{datetime.datetime.now().strftime('%H-%M-%S')}.txt", "Text Files (*.txt)")
        if fname:
            try:
                with open(fname, 'w', encoding='utf-8') as f:
                    for text, _ in self.log_history:
                        f.write(text + "\n")
                self.main.show_toast(_t("DASH_MSG_LOG_SAVED"), False)
            except Exception:
                self.main.show_toast(_t("DASH_MSG_LOG_SAVE_ERR"), True)

    def load(self, name):
        if self.current_server != name:
            self.clear_console() 
            self.current_server = name

        server = self.manager.servers[name]
        self.title_lbl.setText(server.name)
        c_type, c_ver, supports_tps = core.parse_core_info(server.core_name)
        self.desc_lbl.setText(_t("DASH_DESC_CORE_VER", core=c_type, ver=c_ver))
        
        props = self.manager.get_server_properties(name)
        max_p = props.get("max-players", "20")
        self.players_lbl.setText(_t("DASH_PLAYERS", cur=0, max_p=max_p))
        self.uptime_lbl.setText(_t("DASH_UPTIME_ZERO"))
        
        state = "OFFLINE"
        if self.manager.active_instance and self.manager.active_instance.data.name == name: state = self.manager.active_instance.state
        self.update_ui_state(state)
        self.main.run_async(
            lambda path=server.directory: core.ServerManager.get_dir_size_gb(path),
            lambda size, server_name=name: self.on_disk_size_loaded(server_name, size),
        )
        if state == "OFFLINE": 
            for c in [self.card_tps, self.card_ram, self.card_cpu]:
                c.update_data(-1.0, 100)

    def on_disk_size_loaded(self, server_name, size):
        if self.current_server == server_name:
            self.card_disk.update_data(size, 0, f"{size:.2f} GB")

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
            if self.manager.active_instance.data.name == self.current_server: self.update_ui_state(state)

    @Slot(str, str)
    def on_log(self, text, type_):
        if not self.current_server: return
        if "TPS from last" in text: return 
        if self.manager.active_instance and self.manager.active_instance.data.name == self.current_server:
            clean_text = strip_ansi(text.strip())
            if not clean_text: return
            
            self.log_history.append((clean_text, type_))
            
            if self.should_show_log(type_):
                self.append_log_to_widget(clean_text, type_)
                sb = self.console_out.verticalScrollBar()
                sb.setValue(sb.maximum())

    def on_stats(self, ram, tps, disk, uptime, players, cpu):
        if not self.current_server: return
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
        self.append_log_to_widget(msg, "INFO")
        
        self.kill_timer.stop()
        for c in [self.card_tps, self.card_ram, self.card_cpu]:
            c.update_data(-1.0, 100)
        self.players_lbl.setText(self.players_lbl.text().replace(re.search(r'\d+', self.players_lbl.text()).group(), "0", 1))
        self.uptime_lbl.setText(_t("DASH_UPTIME_ZERO"))
        
        if self.is_restarting:
            self.is_restarting = False
            QTimer.singleShot(1000, self.on_start)

    def on_start(self):
        if not self.current_server: return
        self.clear_console() 
        self.console_history[self.current_server] = ""
        cb = core.ServerCallbacks(self.bridge.on_log, self.bridge.on_stats, self.bridge.on_state, self.bridge.on_stop)
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
            self.btn_stop.setStyleSheet(f"background-color: {COLOR_DANGER}; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;")

    def send_cmd(self):
        cmd = self.inp_cmd.text()
        if cmd: 
            self.manager.send_command(cmd)
            self.log_history.append((f"> {cmd}", "INFO"))
            self.append_log_to_widget(f"> {cmd}", "INFO")
            self.inp_cmd.clear()

    def open_folder(self):
        if self.current_server:
            path = self.manager.servers[self.current_server].directory
            try: os.startfile(path)
            except Exception: self.main.show_toast(_t("DASH_MSG_FOLDER_ERR"), True)

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
        self.layout_ui()

    def layout_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40,40,40,40)
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
        self.search_bar.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border: 1px solid {COLOR_BORDER}; padding: 10px; border-radius: 8px;")
        self.search_bar.textChanged.connect(self.filter_props)
        layout.addWidget(self.search_bar)
        self.loading_lbl = QLabel(_t("PROPS_LOADING"))
        self.loading_lbl.setAlignment(Qt.AlignCenter)
        self.loading_lbl.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 14px; font-weight: 600; padding: 14px;")
        self.loading_lbl.hide()
        layout.addWidget(self.loading_lbl)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.container = QWidget()
        self.form = QGridLayout(self.container)
        self.form.setSpacing(15)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)
        self.btn_save = ModernButton(_t("PROPS_BTN_SAVE"), bg_color=COLOR_ACCENT, text_color="white", is_accent=True)
        self.btn_save.setFixedHeight(52)
        self.btn_save.setStyleSheet(self.btn_save.styleSheet() + f"QPushButton {{ background-color: {COLOR_ACCENT_HOVER}; border: 1px solid {COLOR_ACCENT}; font-size: 15px; }}")
        self.btn_save.clicked.connect(self.save_all)
        layout.addWidget(self.btn_save)

    def load(self, name):
        # Backward-compatible alias
        self.begin_load(name)

    def begin_load(self, name):
        self.current_server = name
        self._pending_server = name
        self._load_seq += 1
        seq = self._load_seq
        self.loading_lbl.show()
        self.scroll.hide()
        self.btn_save.setEnabled(False)
        self.search_bar.setEnabled(False)
        self.search_bar.blockSignals(True)
        self.search_bar.clear()
        self.search_bar.blockSignals(False)
        QTimer.singleShot(10, lambda: self._load_properties_deferred(seq))

    def _load_properties_deferred(self, seq):
        if seq != self._load_seq or not self._pending_server:
            return

        while self.form.count():
            item = self.form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.widgets_map = {}
        self.card_order = []
        props = self.manager.get_server_properties(self._pending_server)
        sorted_keys = sorted(props.keys(), key=lambda k: 0 if k in PROPERTY_GUIDE else 1)
        for key in sorted_keys:
            self.add_row(key, props[key])
        self.reflow_cards("")
        self.scroll.show()
        self.loading_lbl.hide()
        self.btn_save.setEnabled(True)
        self.search_bar.setEnabled(True)

    def add_row(self, key, value):
        row = QFrame(self.container)
        row.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 10px;")
        row.setFixedSize(340, 170)
        rl = QVBoxLayout(row)
        rl.setContentsMargins(15,15,15,15)
        rl.setSpacing(8)
        meta = PROPERTY_GUIDE.get(key, {"desc_key": "", "type": "text"})
        hl = QHBoxLayout()
        hl.setSpacing(12)
        lbl_key = QLabel(key, row)
        lbl_key.setStyleSheet("font-size: 14px; font-weight: bold; color: white;")
        desc_text = _t(meta.get("desc_key")) if meta.get("desc_key") else key
        lbl_desc = QLabel(desc_text, row)
        lbl_desc.setStyleSheet(f"font-size: 12px; color: {COLOR_TEXT_SEC};")
        lbl_desc.setWordWrap(True)
        widget = None
        t = meta["type"]
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
            try: widget.setValue(int(value))
            except: pass
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

    def filter_props(self, text):
        self.reflow_cards(text)

    def reflow_cards(self, text):
        text = text.lower().strip()
        visible_keys = []
        for key in self.card_order:
            _, row, desc_text = self.widgets_map[key]
            self.form.removeWidget(row)
            match = (not text) or (text in key.lower()) or (text in desc_text.lower())
            row.setVisible(match)
            if match:
                visible_keys.append(key)

        for idx, key in enumerate(visible_keys):
            _, row, _ = self.widgets_map[key]
            self.form.addWidget(row, idx // 3, idx % 3)

    def save_all(self):
        new_props = {}
        for key, (w, _row, _desc) in self.widgets_map.items():
            t = PROPERTY_GUIDE.get(key, {"type": "text"})["type"]
            val = ""
            if t == "bool": val = "true" if w.isChecked() else "false"
            elif t == "int": val = str(w.value())
            elif t == "combo": val = w.currentText()
            else: val = w.text()
            new_props[key] = val
        self.manager.save_server_properties(self.current_server, new_props)
        self.main.show_toast(_t("PROPS_MSG_SAVED"), False)

    def go_back(self):
        self.main.show_dashboard(self.current_server)

class SettingsPage(QWidget):
    def __init__(self, manager, main):
        super().__init__()
        self.manager = manager
        self.main = main
        self.current_server = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40,40,40,40)
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

        ram_card = QFrame()
        ram_card.setMaximumWidth(520)
        ram_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        ram_card.setFixedHeight(260)
        ram_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        rl = QVBoxLayout(ram_card)
        rl.setContentsMargins(20,20,20,20)
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

        net_card = QFrame()
        net_card.setMaximumWidth(520)
        net_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        net_card.setFixedHeight(260)
        net_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        nl = QVBoxLayout(net_card)
        nl.setContentsMargins(20,20,20,20)
        nl.addWidget(QLabel(_t("SETTINGS_SECTION_NETWORK"), styleSheet=f"font-size: 16px; font-weight: 700; color: {COLOR_TEXT_MAIN};"))
        nl.addWidget(QLabel(_t("SETTINGS_NETWORK_DESC"), styleSheet=f"color:{COLOR_TEXT_SEC};"))
        btn_net = ModernButton(_t("SETTINGS_BTN_OPEN_NETWORK"), bg_color="#27272a")
        btn_net.clicked.connect(lambda: self.main.show_network(self.current_server))
        nl.addWidget(btn_net)
        cards_row.addWidget(net_card)
        cards_row.addStretch()
        self.form.addLayout(cards_row)

        lang_card_wrap = QHBoxLayout()
        lang_card_wrap.setContentsMargins(0, 0, 0, 0)
        lang_card_wrap.setSpacing(0)
        lang_card_wrap.addStretch()

        lang_card = QFrame()
        lang_card.setMaximumWidth(520)
        lang_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        lang_card.setStyleSheet(
            f"background-color: {COLOR_BG_CARD}; border-radius: 12px; border: 1px solid {COLOR_BORDER};"
        )
        ll = QVBoxLayout(lang_card)
        ll.setContentsMargins(20, 18, 20, 18)
        ll.setSpacing(10)

        lang_title = QLabel(_t("SETTINGS_SECTION_LANGUAGE"))
        lang_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {COLOR_TEXT_MAIN};")
        ll.addWidget(lang_title)

        lang_row = QHBoxLayout()
        lang_row.setSpacing(12)
        lang_lbl = QLabel(_t("SETTINGS_LANGUAGE_LABEL"))
        lang_lbl.setStyleSheet(f"color:{COLOR_TEXT_SEC}; font-weight:600;")
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(_t("SETTINGS_LANG_UK"), "uk")
        self.lang_combo.addItem(_t("SETTINGS_LANG_EN"), "en")
        self.lang_combo.setMinimumWidth(180)
        disable_wheel_value_change(self.lang_combo)
        self.lang_combo.currentIndexChanged.connect(self.on_language_changed)
        lang_row.addWidget(lang_lbl)
        lang_row.addStretch()
        lang_row.addWidget(self.lang_combo)
        ll.addLayout(lang_row)

        lang_card_wrap.addWidget(lang_card)
        lang_card_wrap.addStretch()
        self.form.addLayout(lang_card_wrap)

        self.form.addStretch()
        self.add_section_header(_t("SETTINGS_SECTION_DANGER"))
        self.btn_delete = ModernButton(_t("SETTINGS_BTN_DELETE"), bg_color="#2c1515", text_color=COLOR_DANGER, hover_color=COLOR_DANGER)
        self.btn_delete.clicked.connect(self.delete_server)
        self.form.addWidget(self.btn_delete)

        scroll.setWidget(container)
        layout.addWidget(scroll)

    def add_section_header(self, text):
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
            self,
            _t("SETTINGS_DELETE_CONFIRM_TITLE"),
            _t("SETTINGS_DELETE_CONFIRM_TEXT", name=self.current_server),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.btn_delete.setEnabled(False)
        self.main.run_async(
            lambda name=self.current_server: self.manager.delete_server(name),
            self.on_delete_finished,
            lambda _error: self.on_delete_finished(False),
        )

    def on_delete_finished(self, deleted):
        self.btn_delete.setEnabled(True)
        if deleted:
            self.main.show_home()
            self.main.show_toast(_t("SETTINGS_MSG_SERVER_DELETED"), False)
        else:
            self.main.show_toast(_t("SETTINGS_MSG_DELETE_FAILED"), True)
    
    def go_back(self):
        self.main.show_dashboard(self.current_server)

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
        shadow.setColor(QColor(0,0,0,120))
        shadow.setOffset(0,10)
        card.setGraphicsEffect(shadow)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(40,40,40,40)
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
        self.btn_create = ModernButton(_t("CREATE_BTN_CREATE"), bg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, text_color="white", is_accent=True)
        self.btn_create.clicked.connect(self.create)
        cl.addWidget(self.btn_create)
        btn_cancel = ModernButton(_t("CREATE_BTN_CANCEL"), bg_color="transparent")
        btn_cancel.clicked.connect(self.main.show_home)
        cl.addWidget(btn_cancel)
        layout.addWidget(card)

    def browse(self):
        f, _ = QFileDialog.getOpenFileName(self, _t("CREATE_DLG_PICK_JAR"), "", "*.jar")
        if f: self.inp_jar.setText(f)

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
            lambda created: self.on_create_finished(name, created),
            lambda _error: self.on_create_finished(name, False),
        )

    def on_create_finished(self, name, created):
        self.btn_create.setEnabled(True)
        if created:
            self.main.refresh_sidebar()
            self.main.show_dashboard(name)
            self.main.show_toast(_t("CREATE_MSG_CREATED", name=name), False)
        else:
            self.main.show_toast(_t("CREATE_MSG_CREATE_ERR"), True)

class NetworkPage(QWidget):
    def __init__(self, manager, bridge, main):
        super().__init__()
        self.manager = manager
        self.bridge = bridge
        self.main = main
        self.current_server = None
        self.playit_watchdog = QTimer(self)
        self.playit_watchdog.setInterval(1000)
        self.playit_watchdog.timeout.connect(self.sync_playit_state)
        
        self.bridge.playit_signal.connect(self.on_playit_data)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40,40,40,40)
        
        # Header
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
        
        # Cards Row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)

        # IP Card
        card = QFrame()
        card.setFixedSize(520, 430)
        card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(25,25,25,25)
        cl.setSpacing(15)
        
        cl.addWidget(QLabel(_t("NETWORK_IP_CARD_TITLE"), styleSheet=f"color:{COLOR_TEXT_SEC}; font-weight: bold;"))
        
        # Local IP Row
        self.lbl_local = QLabel(_t("NETWORK_LOCAL_DOTS"))
        self.lbl_local.setStyleSheet("font-size: 16px; padding: 5px;")
        self.lbl_local.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(self.lbl_local)
        
        # Public IP Row
        self.lbl_pub = QLabel(_t("NETWORK_PUBLIC_OFF"))
        self.lbl_pub.setStyleSheet("font-size: 16px; color: #71717a; padding: 5px;")
        self.lbl_pub.setTextInteractionFlags(Qt.TextSelectableByMouse)
        cl.addWidget(self.lbl_pub)
        cl.addStretch()
        cards_row.addWidget(card)
        
        # Playit Control
        tun_card = QFrame()
        tun_card.setFixedSize(520, 430)
        tun_card.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border-radius: 12px;")
        tl = QVBoxLayout(tun_card)
        tl.setContentsMargins(25,25,25,25)
        tl.setSpacing(15)
        
        header_tun = QHBoxLayout()
        header_tun.addWidget(QLabel(_t("NETWORK_PLAYIT_TITLE"), styleSheet="font-size: 18px; font-weight: bold; color: white;"))
        btn_dl = QPushButton(_t("NETWORK_BTN_DOWNLOAD"))
        btn_dl.setCursor(Qt.PointingHandCursor)
        btn_dl.setStyleSheet(f"color: {COLOR_ACCENT}; border: none; font-weight: bold; text-align: right;")
        btn_dl.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://playit.gg/download")))
        header_tun.addWidget(btn_dl)
        tl.addLayout(header_tun)
        
        tl.addWidget(QLabel(_t("NETWORK_PLAYIT_DESC"), styleSheet=f"color:{COLOR_TEXT_SEC};"))
        
        # Path Selector
        path_row = QHBoxLayout()
        self.inp_playit_path = QLineEdit()
        self.inp_playit_path.setPlaceholderText(_t("NETWORK_PH_PLAYIT"))
        self.inp_playit_path.setReadOnly(True)
        self.inp_playit_path.setStyleSheet("background-color: #121214; border: 1px solid #3f3f46; border-radius: 8px; padding: 10px 12px;")
        btn_browse_p = ModernButton("📂", bg_color="#27272a")
        btn_browse_p.setFixedWidth(50)
        btn_browse_p.setStyleSheet(btn_browse_p.styleSheet() + "QPushButton { padding: 0px; font-size: 18px; }")
        btn_browse_p.clicked.connect(self.browse_playit)
        path_row.addWidget(self.inp_playit_path)
        path_row.addWidget(btn_browse_p)
        tl.addLayout(path_row)
        
        self.btn_run = ModernButton(_t("NETWORK_BTN_RUN"), bg_color=COLOR_ACCENT, text_color="black", is_accent=True)
        self.btn_run.clicked.connect(self.toggle_playit)
        tl.addWidget(self.btn_run)
        
        # Log area
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

        self.local_ip = "127.0.0.1"
        self.pub_ip = ""
        self.is_running = False

    def load(self, name):
        self.current_server = name
        self.local_ip = f"{core.ServerManager.get_local_ip()}:25565"
        self.lbl_local.setText(_t("NETWORK_LOCAL_LABEL", ip=self.local_ip))
        
        saved_path = self.manager.get_playit_path()
        if saved_path:
            self.inp_playit_path.setText(saved_path)
        
        self.update_ui_state()
        self.playit_watchdog.start()

    def update_ui_state(self):
        if self.manager.playit_instance:
            self.is_running = True
            self.btn_run.setText(_t("NETWORK_BTN_STOP"))
            self.btn_run.setStyleSheet(f"background-color: {COLOR_DANGER}; color: white; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;")
            self.btn_run.set_glow_color(COLOR_DANGER)
            self.inp_playit_path.setEnabled(False)
        else:
            self.is_running = False
            self.btn_run.setText(_t("NETWORK_BTN_RUN"))
            self.btn_run.setStyleSheet(f"background-color: {COLOR_ACCENT}; color: black; border: none; border-radius: 8px; font-weight: bold; font-size: 14px; padding: 0 25px;")
            self.btn_run.set_glow_color(COLOR_ACCENT)
            self.inp_playit_path.setEnabled(True)
            self.lbl_pub.setText(_t("NETWORK_PUBLIC_OFF"))
            self.lbl_pub.setStyleSheet("font-size: 16px; color: #71717a; padding: 5px;")

    def browse_playit(self):
        f, _ = QFileDialog.getOpenFileName(self, _t("NETWORK_DLG_FIND_PLAYIT"), "", "Executable (*.exe)")
        if f:
            self.inp_playit_path.setText(f)
            self.manager.set_playit_path(f)

    def toggle_playit(self):
        if self.is_running:
            self.manager.toggle_playit(None)
            self.update_ui_state()
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
            self.update_ui_state()

    @Slot(str, str)
    def on_playit_data(self, line, pub_ip):
        if line:
            self.playit_log.appendPlainText(line)
            sb = self.playit_log.verticalScrollBar()
            sb.setValue(sb.maximum())
        if pub_ip and pub_ip != self.pub_ip:
            self.pub_ip = pub_ip
            self.lbl_pub.setText(_t("NETWORK_PUBLIC_LABEL", ip=pub_ip))
            self.lbl_pub.setStyleSheet(f"font-size: 16px; color: {COLOR_ACCENT}; font-weight: bold; padding: 5px;")

    def sync_playit_state(self):
        manager_running = bool(self.manager.playit_instance and self.manager.playit_instance.process)
        if self.is_running != manager_running:
            self.update_ui_state()

    def copy_ip(self, text):
        copy_to_clipboard(text)
        self.main.show_toast(_t("NETWORK_MSG_IP_COPIED"), False)

    def go_back(self):
        self.playit_watchdog.stop()
        self.main.show_settings(self.current_server)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(_t("APP_TITLE"))
        self.resize(1300, 800) # Increased Size
        self.manager = core.ServerManager()
        Translator().set_language(self.manager.settings.get("language", "uk"))
        self.setWindowTitle(_t("APP_TITLE"))
        self.bridge = ServerBridge()
        self.thread_pool = QThreadPool.globalInstance()
        self.worker_tasks = set()
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = QFrame()
        self.sidebar.setFixedWidth(260)
        self.sidebar.setStyleSheet(f"background-color: {COLOR_BG_SIDEBAR}; border-right: 1px solid {COLOR_BORDER};")
        sb_layout = QVBoxLayout(self.sidebar)
        sb_layout.setContentsMargins(20, 30, 20, 30)
        sb_layout.setSpacing(20)
        logo = QLabel(_t("SIDEBAR_LOGO"))
        logo.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {COLOR_ACCENT};")
        sb_layout.addWidget(logo)
        self.sidebar_search = QLineEdit()
        self.sidebar_search.setPlaceholderText(_t("SIDEBAR_SEARCH"))
        self.sidebar_search.setStyleSheet(f"background-color: {COLOR_BG_CARD}; border: 1px solid {COLOR_BORDER}; padding: 8px; border-radius: 6px; font-size: 12px;")
        self.sidebar_search.textChanged.connect(self.filter_sidebar_servers)
        sb_layout.addWidget(self.sidebar_search)
        self.cat_all = QLabel(_t("SIDEBAR_ALL_SERVERS"))
        self.cat_all.setStyleSheet(f"color: {COLOR_TEXT_SEC}; font-size: 11px; font-weight: 700; letter-spacing: 1px; margin-top: 10px;")
        sb_layout.addWidget(self.cat_all)
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
        sb_layout.addWidget(self.server_list_scroll)
        btn_new = ModernButton(_t("SIDEBAR_NEW_SERVER"), bg_color="#27272a")
        btn_new.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        sb_layout.addWidget(btn_new)
        main_layout.addWidget(self.sidebar)
        
        # Stack
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
        self.stack.addWidget(self.page_dash)     # 0
        self.stack.addWidget(self.page_create)   # 1
        self.stack.addWidget(self.page_settings) # 2
        self.stack.addWidget(self.page_network)  # 3
        self.stack.addWidget(self.page_home)     # 4
        self.stack.addWidget(self.page_props)    # 5
        self.stack.setCurrentIndex(4)
        main_layout.addWidget(self.stack)
        self.refresh_sidebar()

    def refresh_sidebar(self):
        for i in reversed(range(self.server_list_layout.count())): 
            w = self.server_list_layout.itemAt(i).widget()
            if w: w.setParent(None)
        for name in self.manager.servers:
            server = self.manager.servers[name]
            c_type, c_ver, _ = core.parse_core_info(server.core_name)
            meta = f"{c_type} • {c_ver}"
            is_running = False
            if self.manager.active_instance and self.manager.active_instance.data.name == name:
                if self.manager.active_instance.state != "OFFLINE": is_running = True
            item = ServerListItem(name, meta, is_running, self.on_sidebar_click)
            self.server_list_layout.addWidget(item)

    def filter_sidebar_servers(self, text):
        text = text.lower()
        for i in range(self.server_list_layout.count()):
            widget = self.server_list_layout.itemAt(i).widget()
            if widget:
                if text in widget.server_name.lower(): widget.show()
                else: widget.hide()

    def on_sidebar_click(self, name): self.show_dashboard(name)
    def show_dashboard(self, name): self.stack.setCurrentIndex(0); self.page_dash.load(name); fade_in(self.page_dash)
    def show_home(self): self.stack.setCurrentIndex(4); self.refresh_sidebar()
    def show_settings(self, name): self.stack.setCurrentIndex(2); self.page_settings.load(name); fade_in(self.page_settings)
    def show_network(self, name): self.stack.setCurrentIndex(3); self.page_network.load(name); fade_in(self.page_network)
    def show_properties(self, name): self.stack.setCurrentIndex(5); self.page_props.begin_load(name); fade_in(self.page_props)
    def show_toast(self, msg, is_error=False): ToastNotification(self, msg, is_error)
    def run_async(self, function, on_result, on_error=None):
        task = WorkerTask(function)
        self.worker_tasks.add(task)
        task.signals.result.connect(on_result)
        if on_error:
            task.signals.error.connect(on_error)
        task.signals.finished.connect(lambda: self.worker_tasks.discard(task))
        self.thread_pool.start(task)
    def closeEvent(self, event):
        if self.manager: self.manager.cleanup()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    font = QFont(FONT_FAMILY, 10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
