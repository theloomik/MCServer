"""Graceful stop when Windows signs out or shuts down, and when the GUI hits an unhandled error (ADR 0006)."""

from __future__ import annotations

import ctypes
import logging
import sys
from collections.abc import Callable
from types import TracebackType

from mcserver.application.errors import ServerStopFailed, ServerStopTimedOut
from mcserver.application.server_coordinator import ServerCoordinator

_logger = logging.getLogger(__name__)

CRASH_STOP_TIMEOUT_SECONDS = 30.0


class ShutdownBlocker:
    """Tell Windows why shutdown must wait (``ShutdownBlockReasonCreate``); a no-op elsewhere."""

    def block(self, window_handle: int, reason: str) -> None:
        """Show ``reason`` on Windows' shutdown screen while the server stops."""
        if sys.platform != "win32" or not window_handle:
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.ShutdownBlockReasonCreate.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
            user32.ShutdownBlockReasonCreate(ctypes.c_void_p(window_handle), reason)
        except (AttributeError, OSError):
            _logger.exception("Could not register a shutdown block reason.")

    def unblock(self, window_handle: int) -> None:
        """Remove the reason registered by ``block``."""
        if sys.platform != "win32" or not window_handle:
            return
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.ShutdownBlockReasonDestroy.argtypes = (ctypes.c_void_p,)
            user32.ShutdownBlockReasonDestroy(ctypes.c_void_p(window_handle))
        except (AttributeError, OSError):
            _logger.exception("Could not remove the shutdown block reason.")


class SessionEndHandler:
    """Stop the active server gracefully when Windows ends the session.

    Connected to ``QGuiApplication.commitDataRequest``. The stop runs on the
    GUI thread because Windows waits for this handler; Windows may still
    force-close MCServer after its own limit, in which case the Job Object
    terminates the server and the unclean-shutdown marker remains.
    """

    def __init__(
        self,
        coordinator: ServerCoordinator,
        reason: str,
        window_handle: Callable[[], int],
        blocker: ShutdownBlocker | None = None,
    ) -> None:
        """Stop ``coordinator``'s server; ``reason`` is shown by Windows meanwhile."""
        self._coordinator = coordinator
        self._reason = reason
        self._window_handle = window_handle
        self._blocker = blocker or ShutdownBlocker()

    def __call__(self, *_session_manager: object) -> None:
        """Handle the session-end request."""
        if self._coordinator.active_server_id is None:
            return
        handle = self._window_handle()
        self._blocker.block(handle, self._reason)
        try:
            self._coordinator.stop_server()
        except (ServerStopTimedOut, ServerStopFailed):
            _logger.warning("The server did not stop before the Windows session ended.", exc_info=True)
        finally:
            self._blocker.unblock(handle)


class CrashHandler:
    """``sys.excepthook`` for the GUI: log, try one graceful stop (30 s), then end the application.

    If Java is still running after the attempt, the application exits anyway;
    Windows then closes the Job Object and terminates Java abruptly, and the
    session marker stays so the next launch reports the incident.
    """

    def __init__(
        self,
        coordinator: ServerCoordinator | None,
        exit_application: Callable[[int], None],
        stop_timeout: float = CRASH_STOP_TIMEOUT_SECONDS,
    ) -> None:
        """Stop ``coordinator``'s server and call ``exit_application(1)``."""
        self._coordinator = coordinator
        self._exit_application = exit_application
        self._stop_timeout = stop_timeout
        self.crashed = False

    def __call__(self, exc_type: type[BaseException], exc: BaseException, traceback: TracebackType | None) -> None:
        """Handle one unhandled exception."""
        _logger.critical(
            "Unhandled exception; MCServer will stop the server and exit.", exc_info=(exc_type, exc, traceback)
        )
        if self.crashed:
            return
        self.crashed = True
        if self._coordinator is not None and self._coordinator.active_server_id is not None:
            try:
                self._coordinator.stop_server(self._stop_timeout)
            except Exception:
                _logger.exception("The graceful stop after the unhandled exception did not complete.")
        self._exit_application(1)
