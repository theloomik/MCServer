"""Dark and light themes from the M4 design: tokens and the window stylesheet (no text, no behaviour).

Token names follow the Figma variables (``color/bg/app`` → ``BG_APP``). Older
names remain as aliases so existing code keeps its meaning.

Code reads ``theme.X`` when it builds a widget. ``apply`` switches every token,
the derived tables and ``STYLESHEET`` at once; windows built afterwards use the
new theme (``app.WindowHost`` rebuilds the window for a live switch, M4).
"""

from __future__ import annotations

THEMES = ("dark", "light")
DEFAULT_THEME = "dark"

DARK: dict[str, str] = {
    "BG_APP": "#0b0b0d",
    "BG_SIDEBAR": "#111114",
    "SURFACE_CARD": "#17171a",
    "SURFACE_RAISED": "#1e1e22",
    "SURFACE_HOVER": "#26262b",
    "SURFACE_CONSOLE": "#09090b",
    "SURFACE_BAND": "#1a1a1e",
    "BORDER": "#26262b",
    "BORDER_STRONG": "#36363d",
    "TEXT": "#f4f4f5",
    "TEXT_SECONDARY": "#a1a1aa",
    "TEXT_MUTED": "#8c8c95",
    "TEXT_FAINT": "#52525b",
    "TEXT_ON_ACCENT": "#04130d",
    "ACCENT": "#10b981",
    "ACCENT_HOVER": "#34d399",
    "ACCENT_SUBTLE": "#0e2620",
    "ACCENT_BORDER": "#1b5a45",
    "ACCENT_DISABLED_TEXT": "#1f5a45",
    "DANGER": "#ef4444",
    "DANGER_TEXT": "#f87171",
    "DANGER_SUBTLE": "#2a1314",
    "DANGER_BORDER": "#6b2a2a",
    "DANGER_SUBTLE_BORDER": "#5b2526",
    "DANGER_HOVER": "#3a1718",
    "DANGER_DISABLED_TEXT": "#6b3a3a",
    "DANGER_DISABLED_BORDER": "#3a1f20",
    "WARNING": "#f59e0b",
    "WARNING_TEXT": "#fbbf24",
    "WARNING_SUBTLE": "#2a1f0b",
    "WARNING_SUBTLE_BORDER": "#5a4114",
    "INFO": "#60a5fa",
    "INFO_SUBTLE": "#0f1d2e",
    "INFO_SUBTLE_BORDER": "#23446b",
    "FOCUS": "#93c5fd",
    "CONSOLE_TEXT": "#e4e4e7",
    "CONSOLE_TIMESTAMP": "#84848d",
    "CONSOLE_COMMAND": "#34d399",
}
"""The original M4 theme."""

LIGHT: dict[str, str] = {
    "BG_APP": "#f4f4f5",
    "BG_SIDEBAR": "#fafafa",
    "SURFACE_CARD": "#ffffff",
    "SURFACE_RAISED": "#ffffff",
    "SURFACE_HOVER": "#ececef",
    "SURFACE_CONSOLE": "#fbfbfc",
    "SURFACE_BAND": "#f7f7f8",
    "BORDER": "#e4e4e7",
    "BORDER_STRONG": "#d4d4d8",
    "TEXT": "#18181b",
    "TEXT_SECONDARY": "#3f3f46",
    "TEXT_MUTED": "#5f5f68",
    "TEXT_FAINT": "#a1a1aa",
    "TEXT_ON_ACCENT": "#ffffff",
    "ACCENT": "#047857",
    "ACCENT_HOVER": "#065f46",
    "ACCENT_SUBTLE": "#e3f6ec",
    "ACCENT_BORDER": "#9fdcbf",
    "ACCENT_DISABLED_TEXT": "#7aa894",
    "DANGER": "#dc2626",
    "DANGER_TEXT": "#b91c1c",
    "DANGER_SUBTLE": "#fdeded",
    "DANGER_BORDER": "#f3b4b4",
    "DANGER_SUBTLE_BORDER": "#f5c2c2",
    "DANGER_HOVER": "#fbdcdc",
    "DANGER_DISABLED_TEXT": "#d99a9a",
    "DANGER_DISABLED_BORDER": "#f6d5d5",
    "WARNING": "#b45309",
    "WARNING_TEXT": "#92400e",
    "WARNING_SUBTLE": "#fdf4e3",
    "WARNING_SUBTLE_BORDER": "#f3d39b",
    "INFO": "#1d4ed8",
    "INFO_SUBTLE": "#eaf1fe",
    "INFO_SUBTLE_BORDER": "#bcd0f7",
    "FOCUS": "#2563eb",
    "CONSOLE_TEXT": "#27272a",
    "CONSOLE_TIMESTAMP": "#63636c",
    "CONSOLE_COMMAND": "#047857",
}
"""Light theme: the same roles, contrast checked like the dark one (tests/unit/presentation/test_accessibility.py)."""

PALETTES = {"dark": DARK, "light": LIGHT}
current = DEFAULT_THEME
"""The applied theme."""

# Tokens (set by ``apply``; the dark values are the initial ones).
BG_APP = DARK["BG_APP"]
BG_SIDEBAR = DARK["BG_SIDEBAR"]
SURFACE_CARD = DARK["SURFACE_CARD"]
SURFACE_RAISED = DARK["SURFACE_RAISED"]
SURFACE_HOVER = DARK["SURFACE_HOVER"]
SURFACE_CONSOLE = DARK["SURFACE_CONSOLE"]
SURFACE_BAND = DARK["SURFACE_BAND"]
BORDER = DARK["BORDER"]
BORDER_STRONG = DARK["BORDER_STRONG"]
TEXT = DARK["TEXT"]
TEXT_SECONDARY = DARK["TEXT_SECONDARY"]
TEXT_MUTED = DARK["TEXT_MUTED"]
"""Hints and captions: at least 4.5:1 on every surface (WCAG AA, M4-GUI-07)."""
TEXT_FAINT = DARK["TEXT_FAINT"]
"""Disabled controls, borders and scrollbars only; never text a user must read."""
TEXT_ON_ACCENT = DARK["TEXT_ON_ACCENT"]
ACCENT = DARK["ACCENT"]
ACCENT_HOVER = DARK["ACCENT_HOVER"]
ACCENT_SUBTLE = DARK["ACCENT_SUBTLE"]
ACCENT_BORDER = DARK["ACCENT_BORDER"]
ACCENT_DISABLED_TEXT = DARK["ACCENT_DISABLED_TEXT"]
DANGER = DARK["DANGER"]
DANGER_TEXT = DARK["DANGER_TEXT"]
DANGER_SUBTLE = DARK["DANGER_SUBTLE"]
DANGER_BORDER = DARK["DANGER_BORDER"]
DANGER_SUBTLE_BORDER = DARK["DANGER_SUBTLE_BORDER"]
DANGER_HOVER = DARK["DANGER_HOVER"]
DANGER_DISABLED_TEXT = DARK["DANGER_DISABLED_TEXT"]
DANGER_DISABLED_BORDER = DARK["DANGER_DISABLED_BORDER"]
WARNING = DARK["WARNING"]
WARNING_TEXT = DARK["WARNING_TEXT"]
WARNING_SUBTLE = DARK["WARNING_SUBTLE"]
WARNING_SUBTLE_BORDER = DARK["WARNING_SUBTLE_BORDER"]
INFO = DARK["INFO"]
INFO_SUBTLE = DARK["INFO_SUBTLE"]
INFO_SUBTLE_BORDER = DARK["INFO_SUBTLE_BORDER"]
FOCUS = DARK["FOCUS"]
"""Keyboard focus ring; reads on every surface and is not a status colour."""
CONSOLE_TEXT = DARK["CONSOLE_TEXT"]
CONSOLE_TIMESTAMP = DARK["CONSOLE_TIMESTAMP"]
CONSOLE_COMMAND = DARK["CONSOLE_COMMAND"]

# Aliases used by earlier code (kept in step by ``apply``).
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

STATUS_COLORS: dict[str, str] = {}
TONE_COLORS: dict[str, tuple[str, str, str]] = {}
"""Banner tone → (background, border, foreground)."""
STYLESHEET = ""
ARROW_DOWN = ""
ARROW_UP = ""
"""Image files for the combo and spin box arrows (``appearance`` draws them in the theme's colours)."""

_PRIMARY = "QPushButton#primaryButton, QPushButton#startButton, QPushButton#createServerButton"
_SECONDARY = (
    "QPushButton#secondaryButton, QPushButton#stopButton, QPushButton#openFolderButton, QPushButton#consoleSend"
)
_GHOST = "QPushButton#ghostButton, QPushButton#clearConsole"
_DANGER = "QPushButton#dangerButton, QPushButton#killButton"


def _each(selectors: str, state: str) -> str:
    return ", ".join(f"{part.strip()}{state}" for part in selectors.split(","))


def resolve_theme(setting: str | None, system_dark: bool | None) -> str:
    """Return the theme to show: the user's setting, else the Windows app mode when known, else dark."""
    if setting in THEMES:
        return str(setting)
    if system_dark is None:
        return DEFAULT_THEME
    return "dark" if system_dark else "light"


def set_arrow_images(down: str, up: str) -> None:
    """Use the image files ``down`` and ``up`` for the arrows and rebuild ``STYLESHEET``."""
    global ARROW_DOWN, ARROW_UP, STYLESHEET
    ARROW_DOWN, ARROW_UP = down.replace("\\", "/"), up.replace("\\", "/")
    STYLESHEET = _build_stylesheet()


def _arrow_rules() -> str:
    if not (ARROW_DOWN and ARROW_UP):
        return ""
    return "\n".join(
        (
            f"QComboBox::down-arrow {{ image: url({ARROW_DOWN}); width: 12px; height: 12px; }}",
            f"QSpinBox::up-arrow {{ image: url({ARROW_UP}); width: 10px; height: 10px; }}",
            f"QSpinBox::down-arrow {{ image: url({ARROW_DOWN}); width: 10px; height: 10px; }}",
        )
    )


def apply(name: str) -> None:
    """Switch every token, the derived tables and ``STYLESHEET`` to theme ``name`` (unknown names: dark)."""
    global current, BACKGROUND, SIDEBAR, CARD, CARD_RAISED, ACCENT_DIM, DANGER_DIM, CONSOLE, CONSOLE_ERROR
    global STATUS_COLORS, TONE_COLORS, STYLESHEET
    name = name if name in PALETTES else DEFAULT_THEME
    globals().update(PALETTES[name])
    current = name
    BACKGROUND, SIDEBAR, CARD, CARD_RAISED = BG_APP, BG_SIDEBAR, SURFACE_CARD, SURFACE_RAISED
    ACCENT_DIM, DANGER_DIM, CONSOLE, CONSOLE_ERROR = ACCENT_SUBTLE, DANGER_SUBTLE, SURFACE_CONSOLE, DANGER_TEXT
    STATUS_COLORS = {
        "running": ACCENT,
        "starting": WARNING,
        "stopping": WARNING,
        "killing": DANGER,
        "stopped": TEXT_MUTED,
        "unknown": TEXT_MUTED,
    }
    TONE_COLORS = {
        "error": (DANGER_SUBTLE, DANGER, DANGER_TEXT),
        "notice": (WARNING_SUBTLE, WARNING, WARNING_TEXT),
        "success": (ACCENT_SUBTLE, ACCENT, ACCENT_HOVER),
        "info": (INFO_SUBTLE, INFO, INFO),
    }
    STYLESHEET = _build_stylesheet()


def _build_stylesheet() -> str:
    return f"""
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
{_each(_PRIMARY, ":disabled")} {{ background-color: {ACCENT_SUBTLE}; color: {ACCENT_DISABLED_TEXT}; border-color: {ACCENT_SUBTLE}; }}
{_SECONDARY} {{ background-color: {SURFACE_RAISED}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; }}
{_each(_SECONDARY, ":hover")} {{ background-color: {SURFACE_HOVER}; }}
{_each(_SECONDARY, ":disabled")} {{ color: {TEXT_FAINT}; background-color: {SURFACE_CARD}; border-color: {BORDER}; }}
{_GHOST} {{ background: transparent; color: {TEXT_SECONDARY}; border: 1px solid transparent; }}
{_each(_GHOST, ":hover")} {{ background-color: {SURFACE_RAISED}; color: {TEXT}; }}
{_each(_GHOST, ":disabled")} {{ color: {TEXT_FAINT}; }}
{_DANGER} {{ background-color: {DANGER_SUBTLE}; color: {DANGER_TEXT}; border: 1px solid {DANGER_BORDER}; }}
{_each(_DANGER, ":hover")} {{ background-color: {DANGER_HOVER}; border-color: {DANGER}; }}
{_each(_DANGER, ":disabled")} {{ color: {DANGER_DISABLED_TEXT}; border-color: {DANGER_DISABLED_BORDER}; }}
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
QLabel#dialogTitle {{ font-size: 18px; font-weight: 600; }}
QFrame#dialogCard {{ background-color: {SURFACE_CARD}; border: none; }}
QFrame#dialogCard QLabel {{ background: transparent; }}
QFrame#dialogFooter {{ background-color: {BG_SIDEBAR}; border: none; border-top: 1px solid {BORDER}; }}
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
/* Drop-down and step buttons: no frame of their own (Qt draws a black one otherwise); the arrows stay native. */
QComboBox::drop-down {{ border: none; background: transparent; width: 24px; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; background: transparent; width: 18px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QComboBox::drop-down:hover {{ background-color: {SURFACE_HOVER}; }}
{_arrow_rules()}
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
QFrame[panelBar="band"] {{ border: none; border-bottom: 1px solid {BORDER}; background-color: {SURFACE_BAND}; }}
QLabel#serverTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#serverSubtitle {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#fieldLabel {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#fieldValue {{ color: {TEXT}; font-size: 13px; }}
QLabel#metricValue {{ color: {TEXT}; font-size: 12px; font-weight: 600; }}
QLabel#controlHint {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#controlHint[tone="warning"] {{ color: {WARNING_TEXT}; }}
QLabel#panelTitle {{ color: {TEXT}; font-weight: 600; }}
QLabel#panelCount {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#monoTitle {{ font-family: {MONO_FAMILY}; font-weight: 600; }}
QLabel#folderPath {{
    font-family: {MONO_FAMILY}; font-size: 12px; color: {TEXT};
    background-color: {SURFACE_CONSOLE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 10px;
}}
QLabel#propertyKey {{ font-family: {MONO_FAMILY}; font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel#propertyKey[invalid="true"] {{ color: {DANGER_TEXT}; }}
QLabel#unsavedCount {{ color: {WARNING_TEXT}; font-size: 12px; }}
QLabel#emptyTitle {{ font-size: 14px; font-weight: 600; }}
QLabel#emptyText {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#iconTile {{ background-color: {SURFACE_RAISED}; border-radius: 10px; }}
QLabel#iconTile[tone="accent"] {{ background-color: {ACCENT_SUBTLE}; border: 1px solid {ACCENT_BORDER}; border-radius: 12px; }}

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
QFrame#banner[tone="error"] {{ background-color: {DANGER_SUBTLE}; border-color: {DANGER_SUBTLE_BORDER}; }}
QFrame#banner[tone="notice"] {{ background-color: {WARNING_SUBTLE}; border-color: {WARNING_SUBTLE_BORDER}; }}
QFrame#banner[tone="success"] {{ background-color: {ACCENT_SUBTLE}; border-color: {ACCENT_BORDER}; }}
QFrame#banner[tone="info"] {{ background-color: {INFO_SUBTLE}; border-color: {INFO_SUBTLE_BORDER}; }}
QFrame#banner[tone="error"] QPushButton {{ color: {DANGER_TEXT}; }}
QFrame#banner[tone="notice"] QPushButton {{ color: {WARNING_TEXT}; }}
QFrame#banner[tone="success"] QPushButton {{ color: {ACCENT_HOVER}; }}
QFrame#toast, QFrame#toastMoreRow {{
    background-color: {SURFACE_RAISED}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
}}
QFrame#toast {{ border-left: 3px solid {INFO}; }}
QFrame#toast[tone="error"] {{ border-left-color: {DANGER}; }}
QFrame#toast[tone="notice"] {{ border-left-color: {WARNING}; }}
QFrame#toast[tone="success"] {{ border-left-color: {ACCENT}; }}
QFrame#toast QLabel, QFrame#toastMoreRow QLabel {{ background: transparent; border: none; color: {TEXT}; }}
QLabel#toastMore {{ color: {TEXT_SECONDARY}; }}
QFrame#toast[tone="error"] QPushButton#linkButton {{ color: {DANGER_TEXT}; }}
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
QLabel#welcomeLegacy {{ color: {TEXT_MUTED}; font-size: 12px; }}

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

/* Dialogs over the dimmed window (UX overhaul) */
QFrame#modalCard {{ background-color: {SURFACE_CARD}; border: 1px solid {BORDER_STRONG}; border-radius: 12px; }}
QFrame#modalCard QFrame#dialogCard {{ background: transparent; border: none; }}
QFrame#modalCard QFrame#dialogFooter {{
    border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;
}}
QScrollArea#modalScroll, QScrollArea#modalScroll > QWidget > QWidget {{ background: transparent; border: none; }}
QPushButton#disclosureButton {{
    background: transparent; border: 1px solid transparent; border-radius: 6px;
    color: {TEXT_SECONDARY}; font-weight: 600; padding: 4px 8px 4px 4px; text-align: left;
}}
QPushButton#disclosureButton:hover {{ color: {TEXT}; background-color: {SURFACE_HOVER}; }}
QPushButton#disclosureButton:focus {{ border-color: {FOCUS}; }}

/* Settings and server properties: grouped rows (UX overhaul) */
QDialog#settingsPage QFrame#dialogCard {{ background: transparent; border: none; }}
QDialog#settingsPage QFrame#dialogFooter {{ background: transparent; border-top: 1px solid {BORDER}; }}
QFrame#pageFooter {{ background-color: {BG_APP}; border: none; border-top: 1px solid {BORDER}; }}
QFrame#settingsGroup {{ background-color: {SURFACE_CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#settingsRow {{ background: transparent; border: none; border-top: 1px solid {BORDER}; }}
QFrame#settingsRow[first="true"] {{ border-top: none; }}
QFrame#settingsGroup QLabel {{ background: transparent; border: none; }}
QLabel#settingsSection {{ color: {TEXT}; font-size: 14px; font-weight: 600; }}
QLabel#settingTitle {{ color: {TEXT}; font-size: 13px; }}
QLabel#settingTitle[invalid="true"] {{ color: {DANGER_TEXT}; }}
QLabel#settingStatus {{ color: {TEXT}; font-weight: 600; }}
QLabel#settingStatus[tone="problem"] {{ color: {WARNING_TEXT}; }}
QLabel#monoValue {{ color: {TEXT_SECONDARY}; font-family: {MONO_FAMILY}; font-size: 12px; }}

/* Memory slider (UX overhaul) */
QLabel#memoryValue {{ color: {TEXT}; font-size: 18px; font-weight: 600; min-width: 64px; }}
QLabel#memoryValue[warning="true"] {{ color: {WARNING_TEXT}; }}
QSlider#memorySliderBar::groove:horizontal {{ height: 4px; background: {BORDER_STRONG}; border-radius: 2px; }}
QSlider#memorySliderBar::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider#memorySliderBar::handle:horizontal {{
    background: {SURFACE_CARD}; border: 2px solid {ACCENT}; width: 14px; height: 14px; margin: -7px 0; border-radius: 9px;
}}
QSlider#memorySliderBar::handle:horizontal:hover {{ background: {ACCENT_SUBTLE}; }}
QSlider#memorySliderBar:focus::handle:horizontal {{ border-color: {FOCUS}; }}
QSlider#memorySliderBar::sub-page:horizontal:disabled {{ background: {TEXT_FAINT}; }}
QPushButton#chipButton {{
    background-color: transparent; color: {TEXT_SECONDARY}; border: 1px solid {BORDER_STRONG};
    border-radius: 12px; padding: 3px 10px; font-size: 12px;
}}
QPushButton#chipButton:hover {{ color: {TEXT}; border-color: {TEXT_FAINT}; }}
QPushButton#chipButton:checked {{ color: {ACCENT_HOVER}; background-color: {ACCENT_SUBTLE}; border-color: {ACCENT_BORDER}; }}
QPushButton#chipButton:focus {{ border-color: {FOCUS}; }}
QLabel#jarName {{ color: {TEXT_MUTED}; }}
QLabel#jarName[chosen="true"] {{ color: {TEXT}; font-weight: 600; }}

/* Dashboard: stat tiles and tab-bar actions (UX overhaul) */
QFrame#statTile {{ background-color: {SURFACE_CARD}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#statTile QLabel {{ background: transparent; border: none; }}
QLabel#tileCaption {{ color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px; }}
QLabel#tileValue {{ color: {TEXT}; font-size: 22px; font-weight: 600; }}
QLabel#tileDetail {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#addressValue {{ color: {TEXT}; font-family: {MONO_FAMILY}; font-size: 12px; }}
QPushButton#toolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 6px; }}
QPushButton#toolButton:hover {{ background-color: {SURFACE_HOVER}; }}
QPushButton#toolButton:focus {{ border-color: {FOCUS}; }}
QPushButton#toolButton:disabled {{ background: transparent; }}

/* Keyboard focus (M4-GUI-07): every control shows where the focus is, in a colour no state uses. */
{_PRIMARY}, {_SECONDARY}, {_DANGER}, QPushButton {{ outline: none; }}
{_each(_PRIMARY, ":focus")} {{ border: 1px solid {FOCUS}; }}
{_each(_SECONDARY, ":focus")}, {_each(_DANGER, ":focus")}, {_each(_GHOST, ":focus")} {{ border-color: {FOCUS}; }}
QPushButton#iconButton:focus, QPushButton#refreshServers:focus, QPushButton#addServerButton:focus {{
    background-color: {SURFACE_HOVER};
}}
QPushButton#linkButton:focus, QPushButton#detailsButton:focus {{ text-decoration: underline; }}
QComboBox:focus, QPlainTextEdit:focus, QTableWidget:focus, QListWidget:focus {{ border: 1px solid {FOCUS}; }}
QListWidget#serverList:focus {{ border: none; }}
QCheckBox:focus {{ color: {FOCUS}; }}
QCheckBox::indicator:focus {{ border-color: {FOCUS}; }}
QTabBar::tab:focus {{ color: {FOCUS}; }}
"""


apply(DEFAULT_THEME)
