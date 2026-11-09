"""GUI composition root: the only presentation module that knows about Bootstrap.

``app.py`` builds the backend once, chooses full or degraded mode, creates the
main window and guarantees that backend resources are released exactly once
when the event loop ends. Everything else in ``presentation`` receives
already-built Application services.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from mcserver.bootstrap.server_runtime import build_server_creation, build_server_management, build_server_runtime
from mcserver.infrastructure.java_runtime import JavaRuntimeNotFound, JavaRuntimeResolver
from mcserver.infrastructure.server_configuration_store import JsonServerConfigurationRepository
from mcserver.presentation.i18n import DEFAULT_LANGUAGE, Messages, messages_for
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.paths import servers_root
from mcserver.presentation.services import PresentationServices


def build_services(root: Path, java_resolver: JavaRuntimeResolver | None = None) -> PresentationServices:
    """Build the backend for ``root``; fall back to configuration-only mode when Java is missing.

    The full runtime launches servers from the new configuration store
    (``launch_from_configuration_store=True``), so servers created in the GUI
    can be started. In degraded mode management and creation share one
    repository instance, as they do inside the full runtime.
    """
    try:
        runtime = build_server_runtime(root, java_resolver, launch_from_configuration_store=True)
    except JavaRuntimeNotFound as error:
        repository = JsonServerConfigurationRepository(root)
        return PresentationServices(
            servers_root=root,
            management=build_server_management(root, repository),
            server_creation=build_server_creation(root, repository),
            coordinator=None,
            output=None,
            java_problem=str(error),
            closer=lambda: None,
        )
    return PresentationServices(
        servers_root=root,
        management=runtime.management,
        server_creation=runtime.server_creation,
        coordinator=runtime.coordinator,
        output=runtime.output,
        java_problem=None,
        closer=runtime.close,
    )


def run(app: QApplication, services: PresentationServices, messages: Messages) -> int:
    """Show the main window, run the event loop, then release backend resources once."""
    try:
        window = MainWindow(services, messages)
        window.show()
        return app.exec()
    finally:
        # Background tasks may still use services; let them finish before closing.
        QThreadPool.globalInstance().waitForDone()
        services.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Start the MCServer 2.0 GUI."""
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("MCServer")
    return run(app, build_services(servers_root()), messages_for(DEFAULT_LANGUAGE))
