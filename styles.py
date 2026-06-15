import re

from PySide6.QtCore import QEasingCurve, QPropertyAnimation
from PySide6.QtWidgets import QApplication, QGraphicsOpacityEffect

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
    "prevent-proxy-connections": {"desc_key": "PROP_DESC_PREVENT_PROXY", "type": "bool"},
}

# --- GLOBAL STYLES ---
STYLESHEET = f"""
QMainWindow {{ background-color: {COLOR_BG_MAIN}; }}
QWidget {{ font-family: '{FONT_FAMILY}', sans-serif; color: {COLOR_TEXT_MAIN}; }}

QListWidget {{ background-color: transparent; border: none; outline: none; padding: 10px; }}
QListWidget::item {{ height: 60px; padding-left: 0px; border-radius: 8px; margin-bottom: 5px; color: {COLOR_TEXT_SEC}; font-size: 14px; font-weight: 600; border: none; }}
QListWidget::item:selected {{ background-color: #27272a; color: {COLOR_ACCENT}; border-left: 4px solid {COLOR_ACCENT}; }}
QListWidget::item:hover {{ background-color: #1f1f22; color: {COLOR_TEXT_MAIN}; }}

QScrollBar:vertical {{ border: none; background: {COLOR_BG_MAIN}; width: 6px; margin: 0px; }}
QScrollBar::handle:vertical {{ background: #3f3f46; min-height: 20px; border-radius: 3px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}

QPlainTextEdit {{ background-color: #0c0c0e; border: none; border-radius: 8px; font-family: 'Consolas', monospace; font-size: 13px; color: #e4e4e7; padding: 15px; selection-background-color: #3f3f46; }}

QLineEdit {{ background-color: #121214; border: 1px solid transparent; border-radius: 6px; padding: 10px 12px; color: white; font-size: 13px; }}
QLineEdit:focus {{ border: 1px solid {COLOR_ACCENT}; background-color: #18181b; }}
QLineEdit:hover {{ border: 1px solid #3f3f46; }}
QLineEdit:disabled {{ color: #52525b; background-color: #09090b; }}

QSpinBox {{ background-color: #121214; border: 1px solid transparent; border-radius: 6px; padding: 5px; color: white; font-size: 13px; }}
QSpinBox:focus {{ border: 1px solid {COLOR_ACCENT}; }}

QSlider {{ min-height: 26px; background: transparent; }}
QSlider::groove:horizontal {{ border: none; height: 6px; background: #27272a; margin: 0px; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {COLOR_ACCENT}; border: none; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }}
QSlider::sub-page:horizontal {{ background: {COLOR_ACCENT}; border-radius: 3px; }}

QComboBox {{ background-color: #1c1c1f; border: none; border-radius: 6px; padding: 5px 10px; color: white; }}
QCheckBox {{ color: {COLOR_TEXT_SEC}; spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px; background: #1c1c1f; border: none; }}
QCheckBox::indicator:checked {{ background-color: {COLOR_ACCENT}; }}
QCheckBox::indicator:hover {{ border: 1px solid #52525b; }}

QFrame {{ border: none; }}
QLabel {{ border: none; }}
"""

_ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


def fade_in(widget, duration: int = 200) -> None:
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    widget.fade_anim = QPropertyAnimation(effect, b"opacity")
    widget.fade_anim.setStartValue(0)
    widget.fade_anim.setEndValue(1)
    widget.fade_anim.setDuration(duration)
    widget.fade_anim.setEasingCurve(QEasingCurve.OutQuad)
    widget.fade_anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget.fade_anim.start()


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub('', text)


def copy_to_clipboard(text: str) -> None:
    QApplication.clipboard().setText(text)


def disable_wheel_value_change(widget) -> None:
    widget.wheelEvent = lambda event: event.ignore()
