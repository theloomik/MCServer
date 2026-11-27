"""Presentation tests run without a display."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Measure text with the real Windows fonts when they exist (layout and scaling checks, M4-GUI-07).
_FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
if _FONTS.is_dir():
    os.environ.setdefault("QT_QPA_FONTDIR", str(_FONTS))
