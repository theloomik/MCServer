"""GUI composition root: the only presentation module that knows about Bootstrap.

``app.py`` builds the backend once, creates the main window and guarantees
that backend resources are released exactly once when the event loop ends.
Java is looked up on every start (M1-BE-05), so the backend is always built in
full; a missing Java only disables starting until Java is installed or chosen.
Everything else in ``presentation`` receives already-built Application services.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from mcserver.application.ports import JavaRuntimeProvider
from mcserver.bootstrap.server_runtime import build_server_runtime
from mcserver.presentation.adapters.session_end import CRASH_STOP_TIMEOUT_SECONDS, CrashHandler, SessionEndHandler
from mcserver.presentation.i18n import DEFAULT_LANGUAGE, Messages, messages_for
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.paths import servers_root
from mcserver.presentation.services import PresentationServices

_JAVA_MISSING = "No usable Java runtime was found."


def build_services(root: Path, java_resolver: JavaRuntimeProvider | None = None) -> PresentationServices:
    """Build the backend for ``root``.

    The runtime launches servers from the new configuration store
    (``launch_from_configuration_store=True``), so servers created in the GUI
    can be started. ``java_problem`` describes a missing Java at startup; the
    GUI can detect Java again later without a restart.
    """
    runtime = build_server_runtime(root, java_resolver, launch_from_configuration_store=True)

    def close() -> object:
        # After an unhandled exception the graceful stop was already attempted (30 s).
        return runtime.close(0.0 if services.crashed else None)

    services = PresentationServices(
        servers_root=root,
        management=runtime.management,
        server_creation=runtime.server_creation,
        coordinator=runtime.coordinator,
        output=runtime.output,
        java_problem=None if runtime.java.status().available else _JAVA_MISSING,
        closer=close,
        provisioning=runtime.provisioning,
        java=runtime.java,
        health=runtime.health,
    )
    return services


def run(app: QApplication, services: PresentationServices, messages: Messages) -> int:
    """Show the main window, run the event loop, then release backend resources once."""
    crash_handler = CrashHandler(services.coordinator, app.exit, CRASH_STOP_TIMEOUT_SECONDS)
    previous_hook = sys.excepthook

    def on_unhandled(exc_type: type[BaseException], exc: BaseException, traceback: TracebackType | None) -> None:
        services.crashed = True
        crash_handler(exc_type, exc, traceback)

    sys.excepthook = on_unhandled
    try:
        window = MainWindow(services, messages)
        if services.coordinator is not None:
            session_end = SessionEndHandler(
                services.coordinator, messages.text("session.block_reason"), lambda: int(window.winId())
            )
            app.commitDataRequest.connect(session_end)
        window.show()
        return app.exec()
    finally:
        sys.excepthook = previous_hook
        # Background tasks may still use services; let them finish before closing.
        QThreadPool.globalInstance().waitForDone()
        services.close()


def main(argv: Sequence[str] | None = None) -> int:
    """Start the MCServer 2.0 GUI."""
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("MCServer")
    return run(app, build_services(servers_root()), messages_for(DEFAULT_LANGUAGE))
