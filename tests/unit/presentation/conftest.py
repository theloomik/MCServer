"""Presentation tests run without a display."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
