"""Dark theme: palette and the window stylesheet (no text, no behaviour)."""

from __future__ import annotations

BACKGROUND = "#09090b"
SIDEBAR = "#111113"
CARD = "#18181b"
CARD_RAISED = "#1f1f23"
BORDER = "#27272a"
TEXT = "#fafafa"
TEXT_MUTED = "#a1a1aa"
TEXT_FAINT = "#52525b"
ACCENT = "#10b981"
ACCENT_HOVER = "#34d399"
ACCENT_DIM = "#064e3b"
DANGER = "#ef4444"
DANGER_DIM = "#3f1d1d"
WARNING = "#f59e0b"
CONSOLE = "#0c0c0e"
CONSOLE_TEXT = "#e4e4e7"
CONSOLE_ERROR = "#f87171"

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono, Consolas, monospace"

STATUS_COLORS = {
    "running": ACCENT,
    "starting": WARNING,
    "stopping": WARNING,
    "stopped": TEXT_FAINT,
    "unknown": TEXT_FAINT,
}

STYLESHEET = f"""
QMainWindow, QWidget#central {{ background-color: {BACKGROUND}; }}
QWidget {{ font-family: '{FONT_FAMILY}'; font-size: 13px; color: {TEXT}; }}
QToolTip {{ background-color: {CARD_RAISED}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}

QMenuBar {{ background-color: {SIDEBAR}; color: {TEXT_MUTED}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background-color: {CARD}; color: {TEXT}; border-radius: 4px; }}
QMenu {{ background-color: {CARD}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {CARD_RAISED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QStatusBar {{ background-color: {SIDEBAR}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER}; }}
QStatusBar QLabel {{ color: {TEXT_MUTED}; padding: 2px 8px; }}
QStatusBar::item {{ border: none; }}

QSplitter::handle {{ background-color: {BORDER}; width: 1px; }}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3f3f46; min-height: 24px; border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: #52525b; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3f3f46; min-width: 24px; border-radius: 3px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

/* Sidebar */
QWidget#sidebar {{ background-color: {SIDEBAR}; }}
QLabel#brandMark {{ background-color: {ACCENT}; border-radius: 5px; }}
QLabel#brandTitle {{ color: {ACCENT}; font-size: 20px; font-weight: 700; }}
QLabel#sectionCaption {{ color: {TEXT_MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QPushButton#refreshServers {{
    background: transparent; color: {TEXT_MUTED}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 4px 10px; font-size: 12px;
}}
QPushButton#refreshServers:hover {{ color: {TEXT}; border-color: #3f3f46; background-color: {CARD}; }}
QListWidget#serverList {{ background: transparent; border: none; outline: none; }}
QListWidget#serverList::item {{ border: none; }}
QLabel#serverListEmpty, QLabel#serverListError {{ color: {TEXT_MUTED}; padding: 16px; }}
QLabel#serverListError {{ color: {DANGER}; }}

/* Cards */
QFrame[card="true"] {{ background-color: {CARD}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame[card="true"] QLabel {{ background: transparent; }}
QLabel#serverTitle {{ font-size: 28px; font-weight: 700; }}
QLabel#serverSubtitle {{ color: {TEXT_MUTED}; font-size: 14px; }}
QLabel#fieldLabel {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#fieldValue {{ color: {TEXT}; font-size: 13px; }}
QLabel#controlHint {{ color: {TEXT_MUTED}; font-size: 12px; }}

QLabel#statusPill {{
    border-radius: 13px; padding: 4px 14px; font-weight: 700; font-size: 12px;
    background-color: {CARD_RAISED}; color: {TEXT_MUTED}; border: 1px solid {BORDER};
}}
QLabel#statusPill[status="running"] {{ color: {ACCENT}; border-color: {ACCENT_DIM}; background-color: #0b2a20; }}
QLabel#statusPill[status="starting"], QLabel#statusPill[status="stopping"] {{
    color: {WARNING}; border-color: #4a3410; background-color: #2a1f0a;
}}

QPushButton#startButton, QPushButton#stopButton, QPushButton#openFolderButton {{
    border-radius: 10px; padding: 10px 22px; font-size: 14px; font-weight: 600;
}}
QPushButton#startButton {{ background-color: {ACCENT}; color: #04120c; border: 1px solid {ACCENT}; }}
QPushButton#startButton:hover {{ background-color: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton#stopButton {{ background-color: transparent; color: {DANGER}; border: 1px solid #5b2121; }}
QPushButton#stopButton:hover {{ background-color: {DANGER_DIM}; }}
QPushButton#startButton:disabled, QPushButton#stopButton:disabled {{
    background-color: {CARD_RAISED}; color: {TEXT_FAINT}; border: 1px solid {BORDER};
}}
QPushButton#openFolderButton {{ background-color: {CARD_RAISED}; color: {TEXT}; border: 1px solid {BORDER}; }}
QPushButton#openFolderButton:hover {{ border-color: #3f3f46; background-color: #26262b; }}

QLabel#banner {{ border-radius: 8px; padding: 10px 12px; }}
QLabel#banner[tone="error"] {{ background-color: {DANGER_DIM}; color: #fecaca; border: 1px solid #5b2121; }}
QLabel#banner[tone="notice"] {{ background-color: #2a1f0a; color: #fde68a; border: 1px solid #4a3410; }}

/* Console */
QLabel#consoleTitle {{ font-family: {MONO_FAMILY}; color: {TEXT_MUTED}; font-weight: 700; }}
QPushButton#clearConsole {{
    background: transparent; color: {TEXT_MUTED}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 4px 12px;
}}
QPushButton#clearConsole:hover {{ color: {TEXT}; background-color: {CARD_RAISED}; }}
QPlainTextEdit#console {{
    background-color: {CONSOLE}; color: {CONSOLE_TEXT}; border: none; border-radius: 10px;
    padding: 10px; font-family: {MONO_FAMILY}; font-size: 12px; selection-background-color: #3f3f46;
}}
QLabel#consoleUnavailable {{ color: {TEXT_MUTED}; }}

/* Welcome */
QLabel#welcomeTitle {{ color: #3f3f46; font-size: 34px; font-weight: 700; }}
QLabel#welcomeText {{ color: {TEXT_MUTED}; font-size: 15px; }}
"""
