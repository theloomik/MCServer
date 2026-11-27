"""About MCServer: logo, version, a line on what it does, the license and the project page (M5)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mcserver import APP_NAME, COPYRIGHT, HOMEPAGE, __version__
from mcserver.presentation import icons
from mcserver.presentation.dialogs.form import FormDialog, primary_button
from mcserver.presentation.i18n import Messages


class AboutDialog(FormDialog):
    """A compact card; nothing in it changes anything."""

    def __init__(self, messages: Messages, parent: QWidget | None = None) -> None:
        """Build the card in the current language."""
        super().__init__(messages.text("about.title"), "", parent)
        self.setMinimumWidth(460)
        logo = QLabel(self)
        logo.setObjectName("aboutLogo")
        logo.setFixedSize(56, 56)
        logo.setPixmap(icons.logo_pixmap(56))
        logo.setAccessibleName(APP_NAME)
        self.name_label = QLabel(APP_NAME, self)
        self.name_label.setObjectName("aboutName")
        self.version_label = QLabel(messages.text("about.version", version=__version__), self)
        self.version_label.setObjectName("fieldHint")
        self.version_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        names = QVBoxLayout()
        names.setSpacing(2)
        names.addStretch(1)
        names.addWidget(self.name_label)
        names.addWidget(self.version_label)
        names.addStretch(1)
        identity = QHBoxLayout()
        identity.setSpacing(14)
        identity.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        identity.addLayout(names, 1)
        self.body.addLayout(identity)
        self.body.addSpacing(6)
        self.description_label = QLabel(messages.text("about.description"), self)
        self.description_label.setWordWrap(True)
        self.body.addWidget(self.description_label)
        self.license_label = QLabel(messages.text("about.license", copyright=COPYRIGHT), self)
        self.license_label.setObjectName("fieldHint")
        self.license_label.setWordWrap(True)
        self.body.addWidget(self.license_label)
        self.homepage_button = QPushButton(messages.text("about.homepage"), self)
        self.homepage_button.setObjectName("linkButton")
        self.homepage_button.setIcon(icons.icon("external"))
        self.homepage_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.homepage_button.setToolTip(HOMEPAGE)
        self.homepage_button.setAccessibleDescription(HOMEPAGE)
        self.homepage_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HOMEPAGE)))
        self.body.addWidget(self.homepage_button, 0, Qt.AlignmentFlag.AlignLeft)
        close_button = primary_button(messages.text("about.close"))
        close_button.clicked.connect(self.accept)
        self.add_buttons(close_button)


__all__ = ["AboutDialog"]
