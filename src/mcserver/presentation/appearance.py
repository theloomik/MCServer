"""Choose and apply the dark or light theme, following the Windows app mode when asked to (M4)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from mcserver.presentation import icons, theme


def system_prefers_dark() -> bool | None:
    """Return the Windows app mode (dark or light), or ``None`` when Qt cannot tell.

    Any colour scheme MCServer itself requested is cleared first, so the answer
    is the system's, not the application's own choice.
    """
    if QGuiApplication.instance() is None:
        return None
    hints = QGuiApplication.styleHints()
    hints.unsetColorScheme()
    scheme = hints.colorScheme()
    if scheme == Qt.ColorScheme.Dark:
        return True
    if scheme == Qt.ColorScheme.Light:
        return False
    return None


def resolve(setting: str | None) -> str:
    """Return the theme ``setting`` means now (``None``: the Windows app mode, else dark)."""
    return theme.resolve_theme(setting, system_prefers_dark() if setting not in theme.THEMES else None)


def theme_palette() -> QPalette:
    """Return a ``QPalette`` from the applied theme, for the parts Qt draws itself (arrows, step buttons, tooltips)."""
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: theme.BG_APP,
        QPalette.ColorRole.WindowText: theme.TEXT,
        QPalette.ColorRole.Base: theme.SURFACE_CARD,
        QPalette.ColorRole.AlternateBase: theme.SURFACE_RAISED,
        QPalette.ColorRole.Text: theme.TEXT,
        QPalette.ColorRole.PlaceholderText: theme.TEXT_MUTED,
        QPalette.ColorRole.Button: theme.SURFACE_RAISED,
        QPalette.ColorRole.ButtonText: theme.TEXT,
        QPalette.ColorRole.BrightText: theme.DANGER_TEXT,
        QPalette.ColorRole.ToolTipBase: theme.SURFACE_RAISED,
        QPalette.ColorRole.ToolTipText: theme.TEXT,
        QPalette.ColorRole.Highlight: theme.ACCENT,
        QPalette.ColorRole.HighlightedText: theme.TEXT_ON_ACCENT,
        QPalette.ColorRole.Link: theme.INFO,
        QPalette.ColorRole.Light: theme.SURFACE_HOVER,
        QPalette.ColorRole.Midlight: theme.BORDER,
        QPalette.ColorRole.Mid: theme.BORDER_STRONG,
        QPalette.ColorRole.Dark: theme.BORDER_STRONG,
        QPalette.ColorRole.Shadow: theme.BORDER_STRONG,
    }
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(theme.TEXT_FAINT))
    return palette


ARROW_DIRECTORY = Path(tempfile.gettempdir()) / "mcserver-theme"
"""Where the arrow images live: stylesheets can only load images from files."""


def write_arrow_images(directory: Path = ARROW_DIRECTORY) -> tuple[Path, Path]:
    """Draw the down and up arrows in the applied theme's colour; return their files (reused when present)."""
    directory.mkdir(parents=True, exist_ok=True)
    color = theme.TEXT_SECONDARY
    files: list[Path] = []
    for name in ("chevron-down", "chevron-up"):
        path = directory / f"{name}-{color.lstrip('#')}.png"
        if not path.is_file():
            icons.pixmap(name, color, 12, 2.0).save(str(path), "PNG")
        files.append(path)
    return files[0], files[1]


def apply_appearance(setting: str | None) -> str:
    """Apply the theme ``setting`` asks for and tell Windows, so title bars and native parts match; return it."""
    name = resolve(setting)
    theme.apply(name)
    if QGuiApplication.instance() is not None:
        try:
            down, up = write_arrow_images()
            theme.set_arrow_images(str(down), str(up))
        except OSError:
            pass  # without the images Qt draws no arrows; the controls still work

        # QApplication.setPalette (not QGuiApplication's) also reaches existing widgets.
        QApplication.setPalette(theme_palette())
        hints = QGuiApplication.styleHints()
        if setting in theme.THEMES:
            hints.setColorScheme(Qt.ColorScheme.Dark if name == "dark" else Qt.ColorScheme.Light)
        else:
            # Following Windows: keep Qt on the system scheme so later changes are still reported.
            hints.unsetColorScheme()
    return name


__all__ = ["apply_appearance", "resolve", "system_prefers_dark", "theme_palette", "write_arrow_images"]
