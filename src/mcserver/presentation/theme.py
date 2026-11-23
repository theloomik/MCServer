"""Dark theme from the M4 design: tokens and the window stylesheet (no text, no behaviour).

Token names follow the Figma variables (``color/bg/app`` → ``BG_APP``). Older
names remain as aliases so existing code keeps its meaning.
"""

from __future__ import annotations

BG_APP = "#0b0b0d"
BG_SIDEBAR = "#111114"
SURFACE_CARD = "#17171a"
SURFACE_RAISED = "#1e1e22"
SURFACE_HOVER = "#26262b"
SURFACE_CONSOLE = "#09090b"
BORDER = "#26262b"
BORDER_STRONG = "#36363d"
TEXT = "#f4f4f5"
TEXT_SECONDARY = "#a1a1aa"
TEXT_MUTED = "#71717a"
TEXT_FAINT = "#52525b"
TEXT_ON_ACCENT = "#04130d"
ACCENT = "#10b981"
ACCENT_HOVER = "#34d399"
ACCENT_SUBTLE = "#0e2620"
DANGER = "#ef4444"
DANGER_TEXT = "#f87171"
DANGER_SUBTLE = "#2a1314"
WARNING = "#f59e0b"
WARNING_TEXT = "#fbbf24"
WARNING_SUBTLE = "#2a1f0b"
INFO = "#60a5fa"
INFO_SUBTLE = "#0f1d2e"
CONSOLE_TEXT = "#e4e4e7"
CONSOLE_TIMESTAMP = "#52525b"
CONSOLE_COMMAND = "#34d399"

# Aliases used by earlier code.
BACKGROUND = BG_APP
SIDEBAR = BG_SIDEBAR
CARD = SURFACE_CARD
CARD_RAISED = SURFACE_RAISED
ACCENT_DIM = ACCENT_SUBTLE
DANGER_DIM = DANGER_SUBTLE
CONSOLE = SURFACE_CONSOLE
CONSOLE_ERROR = DANGER_TEXT

FONT_FAMILY = "Segoe UI"
MONO_FAMILY = "Cascadia Mono, Consolas, monospace"

STATUS_COLORS = {
    "running": ACCENT,
    "starting": WARNING,
    "stopping": WARNING,
    "killing": DANGER,
    "stopped": TEXT_FAINT,
    "unknown": TEXT_FAINT,
}
TONE_COLORS = {
    "error": (DANGER_SUBTLE, DANGER, DANGER_TEXT),
    "notice": (WARNING_SUBTLE, WARNING, WARNING_TEXT),
    "success": (ACCENT_SUBTLE, ACCENT, ACCENT_HOVER),
    "info": (INFO_SUBTLE, INFO, INFO),
}
"""Banner tone → (background, border, foreground)."""

_PRIMARY = "QPushButton#primaryButton, QPushButton#startButton, QPushButton#createServerButton"
_SECONDARY = (
    "QPushButton#secondaryButton, QPushButton#stopButton, QPushButton#openFolderButton, QPushButton#consoleSend"
)
_GHOST = "QPushButton#ghostButton, QPushButton#clearConsole"
_DANGER = "QPushButton#dangerButton, QPushButton#killButton"


def _each(selectors: str, state: str) -> str:
    return ", ".join(f"{part.strip()}{state}" for part in selectors.split(","))


STYLESHEET = f"""
QMainWindow, QWidget#central {{ background-color: {BG_APP}; }}
QWidget {{ font-family: '{FONT_FAMILY}'; font-size: 13px; color: {TEXT}; }}
QToolTip {{ background-color: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; padding: 6px; }}

QMenuBar {{ background-color: {BG_SIDEBAR}; color: {TEXT_SECONDARY}; border-bottom: 1px solid {BORDER}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 4px 10px; background: transparent; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: {SURFACE_RAISED}; color: {TEXT}; }}
QMenu {{ background-color: {SURFACE_RAISED}; border: 1px solid {BORDER_STRONG}; padding: 4px; border-radius: 8px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {SURFACE_HOVER}; }}
QMenu::item:disabled {{ color: {TEXT_FAINT}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QStatusBar {{ background-color: {BG_SIDEBAR}; color: {TEXT_MUTED}; border-top: 1px solid {BORDER}; min-height: 28px; }}
QStatusBar QLabel {{ color: {TEXT_MUTED}; padding: 0px 6px; font-size: 12px; }}
QStatusBar QLabel#javaStatus {{ color: {TEXT_SECONDARY}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QPushButton {{
    background: transparent; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_STRONG};
    border-radius: 4px; padding: 2px 8px; margin: 3px 2px; font-size: 12px;
}}
QStatusBar QPushButton:hover {{ color: {TEXT}; background-color: {SURFACE_RAISED}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; min-height: 24px; border-radius: 3px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER_STRONG}; min-width: 24px; border-radius: 3px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

/* Buttons: primary, secondary, ghost, danger, icon (32 px high) */
{_PRIMARY}, {_SECONDARY}, {_GHOST}, {_DANGER} {{
    border-radius: 6px; padding: 6px 14px; font-weight: 600; min-height: 18px;
}}
{_PRIMARY} {{ background-color: {ACCENT}; color: {TEXT_ON_ACCENT}; border: 1px solid {ACCENT}; }}
{_each(_PRIMARY, ":hover")} {{ background-color: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
{_each(_PRIMARY, ":disabled")} {{ background-color: {ACCENT_SUBTLE}; color: #1f5a45; border-color: {ACCENT_SUBTLE}; }}
{_SECONDARY} {{ background-color: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; }}
{_each(_SECONDARY, ":hover")} {{ background-color: {SURFACE_HOVER}; }}
{_each(_SECONDARY, ":disabled")} {{ color: {TEXT_FAINT}; background-color: {SURFACE_CARD}; border-color: {BORDER}; }}
{_GHOST} {{ background: transparent; color: {TEXT_SECONDARY}; border: 1px solid transparent; }}
{_each(_GHOST, ":hover")} {{ background-color: {SURFACE_RAISED}; color: {TEXT}; }}
{_each(_GHOST, ":disabled")} {{ color: {TEXT_FAINT}; }}
{_DANGER} {{ background-color: {DANGER_SUBTLE}; color: {DANGER_TEXT}; border: 1px solid #6b2a2a; }}
{_each(_DANGER, ":hover")} {{ background-color: #3a1718; border-color: {DANGER}; }}
{_each(_DANGER, ":disabled")} {{ color: #6b3a3a; border-color: #3a1f20; }}
QPushButton#iconButton, QPushButton#refreshServers, QPushButton#addServerButton {{
    background: transparent; border: none; border-radius: 6px; padding: 6px; min-width: 16px;
}}
QPushButton#iconButton:hover, QPushButton#refreshServers:hover, QPushButton#addServerButton:hover {{
    background-color: {SURFACE_RAISED};
}}
QPushButton#linkButton, QPushButton#detailsButton {{
    background: transparent; border: none; padding: 0px 4px; font-weight: 600;
}}
QPushButton#linkButton:hover, QPushButton#detailsButton:hover {{ text-decoration: underline; }}

/* Sidebar */
QWidget#sidebar {{ background-color: {BG_SIDEBAR}; border-right: 1px solid {BORDER}; }}
QLabel#brandMark {{ background-color: {ACCENT}; border-radius: 6px; }}
QLabel#brandTitle {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
QLabel#sectionCaption {{ color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
QListWidget#serverList {{ background: transparent; border: none; outline: none; }}
QListWidget#serverList::item {{ border: none; }}
QLabel#serverListEmpty, QLabel#serverListError {{ color: {TEXT_MUTED}; padding: 10px; font-size: 12px; }}
QLabel#serverListError {{ color: {DANGER_TEXT}; }}
QFrame#sidebarFooter {{ border: none; border-top: 1px solid {BORDER}; }}
QFrame#sidebarFooter QPushButton#ghostButton {{ text-align: left; padding-left: 10px; }}

/* Dialogs and forms */
QDialog#createServerDialog, QDialog#formDialog {{ background-color: {BG_APP}; }}
QComboBox {{
    background-color: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    border-radius: 6px; padding: 5px 10px; min-height: 20px;
}}
QComboBox:hover {{ border-color: {TEXT_FAINT}; }}
QComboBox:disabled {{ color: {TEXT_FAINT}; background-color: {SURFACE_CARD}; border-color: {BORDER}; }}
QComboBox QAbstractItemView {{
    background-color: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    selection-background-color: {ACCENT_SUBTLE}; outline: none;
}}
QLabel#dialogTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#dialogSubtitle {{ color: {TEXT_SECONDARY}; font-size: 13px; }}
QLabel#formLabel {{ color: {TEXT}; font-size: 13px; font-weight: 600; padding-bottom: 2px; }}
QLabel#fieldHint {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#fieldError {{ color: {DANGER_TEXT}; font-size: 12px; }}
QLabel#errorDetails {{
    color: {TEXT_SECONDARY}; font-family: {MONO_FAMILY}; font-size: 11px;
    background-color: {SURFACE_CONSOLE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px;
}}
QLineEdit, QSpinBox {{
    background-color: {SURFACE_CONSOLE}; color: {TEXT}; border: 1px solid {BORDER_STRONG};
    border-radius: 6px; padding: 6px 10px; font-size: 13px; selection-background-color: {ACCENT_SUBTLE};
}}
QLineEdit:hover, QSpinBox:hover {{ border-color: {TEXT_FAINT}; }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled {{ color: {TEXT_FAINT}; border-color: {BORDER}; }}
QLineEdit[readOnly="true"] {{ color: {TEXT_SECONDARY}; }}
QLineEdit[invalid="true"], QComboBox[invalid="true"], QSpinBox[invalid="true"] {{ border-color: {DANGER}; }}
QSpinBox QLineEdit {{ background: transparent; border: none; padding: 0px 0px 0px 6px; }}
QProgressBar#creationProgress {{ background-color: {SURFACE_HOVER}; border: none; border-radius: 2px; }}
QProgressBar#creationProgress::chunk {{ background-color: {ACCENT}; border-radius: 2px; }}
QCheckBox {{ spacing: 10px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px; border: 1px solid {BORDER_STRONG}; background-color: {SURFACE_CONSOLE};
}}
QCheckBox::indicator:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:disabled {{ background-color: {SURFACE_CARD}; border-color: {BORDER}; }}
QCheckBox:disabled {{ color: {TEXT_FAINT}; }}

/* Cards and panels */
QFrame[card="true"] {{ background-color: {SURFACE_CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame[card="true"] QLabel {{ background: transparent; border: none; }}
QFrame[panelBar="top"] {{ border: none; border-bottom: 1px solid {BORDER}; background: transparent; }}
QFrame[panelBar="bottom"] {{ border: none; border-top: 1px solid {BORDER}; background: transparent; }}
QFrame[panelBar="band"] {{ border: none; border-bottom: 1px solid {BORDER}; background-color: #1a1a1e; }}
QLabel#serverTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#serverSubtitle {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#fieldLabel {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#fieldValue {{ color: {TEXT}; font-size: 13px; }}
QLabel#metricValue {{ color: {TEXT}; font-size: 12px; font-weight: 600; }}
QLabel#controlHint {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#controlHint[tone="warning"] {{ color: {WARNING_TEXT}; }}
QLabel#panelTitle {{ color: {TEXT}; font-weight: 600; }}
QLabel#panelCount {{ color: {TEXT_FAINT}; font-size: 12px; }}
QLabel#monoTitle {{ font-family: {MONO_FAMILY}; font-weight: 600; }}
QLabel#propertyKey {{ font-family: {MONO_FAMILY}; font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel#propertyKey[invalid="true"] {{ color: {DANGER_TEXT}; }}
QLabel#unsavedCount {{ color: {WARNING_TEXT}; font-size: 12px; }}
QLabel#emptyTitle {{ font-size: 14px; font-weight: 600; }}
QLabel#emptyText {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#iconTile {{ background-color: {SURFACE_RAISED}; border-radius: 10px; }}
QLabel#iconTile[tone="accent"] {{ background-color: {ACCENT_SUBTLE}; border: 1px solid #1b5a45; border-radius: 12px; }}

QLabel#statusPill {{
    border-radius: 11px; padding: 2px 10px 2px 8px; font-weight: 600; font-size: 12px;
    background-color: {SURFACE_RAISED}; color: {TEXT_SECONDARY};
}}
QLabel#statusPill[status="running"] {{ color: {ACCENT_HOVER}; background-color: {ACCENT_SUBTLE}; }}
QLabel#statusPill[status="starting"], QLabel#statusPill[status="stopping"] {{
    color: {WARNING_TEXT}; background-color: {WARNING_SUBTLE};
}}
QLabel#statusPill[status="killing"] {{ color: {DANGER_TEXT}; background-color: {DANGER_SUBTLE}; }}

QFrame#banner {{ border-radius: 8px; border: 1px solid {BORDER}; }}
QFrame#banner QLabel {{ background: transparent; border: none; color: {TEXT}; }}
QFrame#banner[tone="error"] {{ background-color: {DANGER_SUBTLE}; border-color: #5b2526; }}
QFrame#banner[tone="notice"] {{ background-color: {WARNING_SUBTLE}; border-color: #5a4114; }}
QFrame#banner[tone="success"] {{ background-color: {ACCENT_SUBTLE}; border-color: #1b5a45; }}
QFrame#banner[tone="info"] {{ background-color: {INFO_SUBTLE}; border-color: #23446b; }}
QFrame#banner[tone="error"] QPushButton {{ color: {DANGER_TEXT}; }}
QFrame#banner[tone="notice"] QPushButton {{ color: {WARNING_TEXT}; }}
QFrame#banner[tone="success"] QPushButton {{ color: {ACCENT_HOVER}; }}
QFrame#banner[tone="info"] QPushButton {{ color: {INFO}; }}

/* Console */
QLabel#consoleTitle {{ color: {TEXT}; font-weight: 600; }}
QPlainTextEdit#console {{
    background-color: {SURFACE_CONSOLE}; color: {CONSOLE_TEXT}; border: none;
    padding: 8px 12px; font-family: {MONO_FAMILY}; font-size: 12px; selection-background-color: {BORDER_STRONG};
}}
QLabel#consolePrompt {{ color: {CONSOLE_COMMAND}; font-family: {MONO_FAMILY}; font-weight: 700; }}
QLabel#consolePrompt:disabled {{ color: {TEXT_FAINT}; }}
QLineEdit#consoleInput {{ font-family: {MONO_FAMILY}; font-size: 12px; }}
QLabel#consoleUnavailable {{ color: {TEXT_MUTED}; padding: 16px; background-color: {SURFACE_CONSOLE}; }}

/* Welcome */
QLabel#welcomeTitle {{ color: {TEXT}; font-size: 22px; font-weight: 600; }}
QLabel#welcomeText {{ color: {TEXT_SECONDARY}; font-size: 13px; }}
QLabel#welcomeLegacy {{ color: {TEXT_FAINT}; font-size: 12px; }}

/* Tabs */
QTabWidget#dashboardTabs::pane {{ border: none; border-top: 1px solid {BORDER}; top: -1px; }}
QTabWidget#dashboardTabs QTabBar {{ qproperty-drawBase: 0; }}
QTabWidget#dashboardTabs QTabBar::tab {{
    background: transparent; color: {TEXT_MUTED}; padding: 9px 14px; margin-right: 4px;
    border: none; border-bottom: 2px solid transparent; font-weight: 600;
}}
QTabWidget#dashboardTabs QTabBar::tab:hover {{ color: {TEXT_SECONDARY}; }}
QTabWidget#dashboardTabs QTabBar::tab:selected {{ color: {TEXT}; border-bottom-color: {ACCENT}; }}

/* Tables */
QTableWidget {{
    background-color: {SURFACE_CARD}; border: none; gridline-color: transparent;
    selection-background-color: {ACCENT_SUBTLE}; selection-color: {TEXT}; outline: none;
}}
QTableWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {BORDER}; color: {TEXT_SECONDARY}; }}
QTableWidget::item:selected {{ background-color: {ACCENT_SUBTLE}; color: {TEXT}; }}
QHeaderView::section {{
    background-color: {SURFACE_CARD}; color: {TEXT_MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 8px; font-size: 11px; font-weight: 600;
}}
QProgressBar {{ background-color: {SURFACE_HOVER}; border: none; border-radius: 2px; }}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 2px; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QListWidget#versionList {{
    background-color: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
}}
QListWidget#versionList::item {{ padding: 5px 8px; border-radius: 6px; }}
QListWidget#versionList::item:hover {{ background-color: {BORDER}; }}
QListWidget#versionList::item:selected {{ background-color: {ACCENT_SUBTLE}; color: {TEXT}; }}
"""
