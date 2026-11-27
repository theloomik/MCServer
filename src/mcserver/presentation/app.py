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

from PySide6.QtCore import QLocale, QThreadPool
from PySide6.QtWidgets import QApplication

from mcserver.application.ports import JavaRuntimeProvider
from mcserver.bootstrap.server_runtime import build_server_runtime
from mcserver.infrastructure.psutil_metrics import total_memory_mb
from mcserver.presentation import icons
from mcserver.presentation.adapters.session_end import CRASH_STOP_TIMEOUT_SECONDS, CrashHandler, SessionEndHandler
from mcserver.presentation.appearance import apply_appearance
from mcserver.presentation.i18n import Messages, messages_for, resolve_language
from mcserver.presentation.main_window import MainWindow
from mcserver.presentation.paths import servers_root
from mcserver.presentation.services import PresentationServices

_JAVA_MISSING = "No usable Java runtime was found."


def build_services(root: Path, java_resolver: JavaRuntimeProvider | None = None) -> PresentationServices:
    """Build the backend for ``root``.

    The runtime launches servers from the configuration store (ADR 0009);
    MCServer 0.9.1 servers are offered for import at startup. ``java_problem`` describes a missing Java at startup; the
    GUI can detect Java again later without a restart.
    """
    runtime = build_server_runtime(root, java_resolver)

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
        settings=runtime.settings,
        adoption=runtime.adoption,
        properties=runtime.properties,
        metrics=runtime.metrics,
        backups=runtime.backups,
        activity=runtime.activity,
        auto_restart=runtime.auto_restart,
        address=runtime.address,
        scheduled_backups=runtime.scheduled_backups,
        worlds=runtime.worlds,
        jar_catalog=runtime.jar_catalog,
        system_memory_mb=total_memory_mb(),
    )
    # A restore cut off by a crash is repaired before anything else touches the server folders.
    runtime.backups.recover_interrupted_restores()
    return services


class WindowHost:
    """Own the main window; on a language or theme change, replace it with one built anew.

    Services (and running servers) are untouched: the new window reads the same
    coordinator, output buffer and stores, so the console history, status and
    selection come back; the old window only releases its timers and subscriptions.
    """

    def __init__(self, services: PresentationServices, messages: Messages) -> None:
        """Create the first window."""
        self._services = services
        self.window = self._create(messages)

    def _create(self, messages: Messages) -> MainWindow:
        window = MainWindow(self._services, messages, first_run_guide=True)
        window.language_change_requested.connect(self.switch_language)
        return window

    def switch_language(self, language: str) -> MainWindow:
        """Show the window again in ``language`` with the same geometry, server and tab; return the new window."""
        old = self.window
        state = old.view_state()
        maximized = old.isMaximized()
        geometry = old.geometry()
        new = self._create(messages_for(language))
        new.setGeometry(geometry)
        new.restore_view_state(state)
        if maximized:
            new.showMaximized()
        elif old.isVisible():
            new.show()
        self.window = new
        old.release()
        old.hide()
        old.deleteLater()
        return new


def run(app: QApplication, services: PresentationServices, messages: Messages) -> int:
    """Show the main window, run the event loop, then release backend resources once."""
    crash_handler = CrashHandler(services.coordinator, app.exit, CRASH_STOP_TIMEOUT_SECONDS)
    previous_hook = sys.excepthook

    def on_unhandled(exc_type: type[BaseException], exc: BaseException, traceback: TracebackType | None) -> None:
        services.crashed = True
        crash_handler(exc_type, exc, traceback)

    sys.excepthook = on_unhandled
    try:
        # The first window is built in the chosen theme (dark, light, or the Windows app mode).
        apply_appearance(services.settings.current.theme if services.settings is not None else None)
        host = WindowHost(services, messages)
        if services.coordinator is not None:
            session_end = SessionEndHandler(
                services.coordinator, messages.text("session.block_reason"), lambda: int(host.window.winId())
            )
            app.commitDataRequest.connect(session_end)
        host.window.show()
        return app.exec()
    finally:
        sys.excepthook = previous_hook
        # Background tasks may still use services; let them finish before closing.
        QThreadPool.globalInstance().waitForDone()
        services.close()


APP_USER_MODEL_ID = "MCServer.MCServer.2"
"""Lets Windows show MCServer's own icon on the taskbar, not Python's, and group its windows together."""


def _use_own_taskbar_entry() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):  # an old or unusual Windows keeps the default entry; nothing else depends on it
        pass


def main(argv: Sequence[str] | None = None) -> int:
    """Start the MCServer 2.0 GUI."""
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(list(sys.argv if argv is None else argv))
    app.setApplicationName("MCServer")
    app.setWindowIcon(icons.app_icon())  # every window, including one rebuilt after a language change
    _use_own_taskbar_entry()
    services = build_services(servers_root())
    setting = services.settings.current.language if services.settings is not None else None
    return run(app, services, messages_for(resolve_language(setting, QLocale.system().name())))
