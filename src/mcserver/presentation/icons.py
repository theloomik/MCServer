"""The icon set from the M4 design: 24×24 SVG paths, stroke 2, tinted per use (no files, no text)."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from mcserver.presentation import theme

_STROKED = {
    "restart": '<path d="M20 11a8 8 0 1 0-2.34 5.66"/><path d="M20 4v7h-7"/>',
    "kill": '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "import": '<path d="M12 20V9M7 14l5-5 5 5M5 4h14"/>',
    "check": '<path d="m5 12 5 5 9-10"/>',
    "alert": '<path d="M12 3 2 21h20z"/><path d="M12 10v4M12 17.5v.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "settings": (
        '<path d="M4 6h9M19 6h1M4 12h3M11 12h9M4 18h11M19 18h1"/>'
        '<circle cx="16" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>'
    ),
    "terminal": '<path d="m4 17 6-5-6-5M12 19h8"/>',
    "copy": (
        '<rect x="8" y="8" width="12" height="12" rx="2"/>'
        '<path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'
    ),
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "server": (
        '<rect x="3" y="4" width="18" height="7" rx="2"/><rect x="3" y="13" width="18" height="7" rx="2"/>'
        '<path d="M7 7.5h.01M7 16.5h.01"/>'
    ),
    "world": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "archive": '<rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10h14V9M10 13h4"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "save": '<path d="M5 3h11l3 3v13a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M7 3v5h8V3M7 21v-7h10v7"/>',
    "external": '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
    "java": (
        '<path d="M5 10h12v5a5 5 0 0 1-5 5h-2a5 5 0 0 1-5-5zM17 11h1.5a2.5 2.5 0 0 1 0 5H17'
        'M9 3c-1 1.5 1 2 0 4M13 3c-1 1.5 1 2 0 4"/>'
    ),
}
_FILLED = {
    "play": '<path d="M7 4.5v15l12-7.5z"/>',
    "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
}
NAMES = frozenset(_STROKED) | frozenset(_FILLED)


def _svg(name: str, color: str) -> bytes:
    if name in _FILLED:
        body, paint = _FILLED[name], f'fill="{color}" stroke="none"'
    else:
        body, paint = _STROKED[name], f'fill="none" stroke="{color}"'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" {paint} '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode()


@lru_cache(maxsize=256)
def pixmap(name: str, color: str = theme.TEXT_SECONDARY, size: int = 16, scale: float = 2.0) -> QPixmap:
    """Return ``name`` drawn in ``color`` at ``size`` logical pixels (crisp on high-DPI screens)."""
    renderer = QSvgRenderer(QByteArray(_svg(name, color)))
    device = max(1, round(size * scale))
    image = QPixmap(device, device)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, device, device))
    painter.end()
    image.setDevicePixelRatio(scale)
    return image


def icon(name: str, color: str = theme.TEXT_SECONDARY, size: int = 16, disabled: str = theme.TEXT_FAINT) -> QIcon:
    """Return a ``QIcon`` with a dimmed disabled state."""
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    result.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return result


__all__ = ["NAMES", "icon", "pixmap"]
