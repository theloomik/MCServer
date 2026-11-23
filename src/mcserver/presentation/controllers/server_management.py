"""Edit, delete and import servers, legacy migration and application settings (M2 GUI)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal

from mcserver.application.server_adoption import FolderContents
from mcserver.application.server_management import DeletedServer, LegacyImportResult
from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.errors import UserMessage, describe_error
from mcserver.presentation.services import PresentationServices
from mcserver.presentation.workers import BackgroundRunner

_logger = logging.getLogger(__name__)


class ManagementController(QObject):
    """Run installation-level operations through the application use cases.

    Small changes (edit, settings) run synchronously and return an error
    message or ``None``. Slow ones (delete, folder copy, legacy import) run in
    the background and report through signals. Business rules stay in the
    use cases; this controller only translates results into messages.
    """

    changed = Signal(object)  # str | None: the server to select after a change
    message = Signal(object)  # UserMessage for the status bar
    failed = Signal(object)  # UserMessage
    busy_changed = Signal(bool)
    copy_progress = Signal(int, int)  # bytes copied, total bytes
    legacy_imported = Signal(object)  # LegacyImportResult

    def __init__(self, services: PresentationServices, runner: BackgroundRunner, parent: QObject | None = None) -> None:
        """Use ``services``; background work goes through ``runner``."""
        super().__init__(parent)
        self._services = services
        self._runner = runner
        self._busy = False
        # Progress is reported from the copy thread; deliver it on the GUI thread.
        self._progress_relay = _ProgressRelay(self)
        self._progress_relay.progress.connect(self.copy_progress, Qt.ConnectionType.QueuedConnection)

    @property
    def busy(self) -> bool:
        """Return whether a background operation is running."""
        return self._busy

    @property
    def servers_root(self) -> Path:
        """Return the managed servers folder."""
        return self._services.servers_root

    def server_folder(self, configuration: ServerConfiguration) -> Path:
        """Return the folder of ``configuration``."""
        return self._services.servers_root / configuration.directory

    def jar_files(self, configuration: ServerConfiguration) -> tuple[str, ...]:
        """Return the JAR files in the server's folder (always including the configured one)."""
        found: tuple[str, ...] = ()
        if self._services.adoption is not None:
            try:
                found = self._services.adoption.inspect(str(self.server_folder(configuration))).jar_files
            except Exception:
                _logger.info("Could not list the JAR files of %r.", configuration.server_id, exc_info=True)
        return found if configuration.jar_file in found else (configuration.jar_file, *found)

    # --- edit (M2-GUI-03) ---------------------------------------------------------------------

    def save_edit(
        self,
        server_id: str,
        *,
        display_name: str,
        memory_mb: int,
        jar_file: str,
        jvm_arguments: tuple[str, ...],
        java_path: str | None,
    ) -> UserMessage | None:
        """Store the edited settings; return an error message, or ``None`` on success."""
        try:
            updated = self._services.management.update_server(
                server_id,
                display_name=display_name,
                memory_mb=memory_mb,
                jar_file=jar_file,
                jvm_arguments=jvm_arguments,
                java_path=java_path if java_path else None,
            )
        except Exception as error:
            return describe_error(error)
        self.message.emit(UserMessage("edit.saved", {"name": updated.name}))
        self.changed.emit(server_id)
        return None

    # --- delete (M2-GUI-04) -----------------------------------------------------------------------

    def delete(self, configuration: ServerConfiguration, *, remove_files: bool) -> None:
        """Delete ``configuration`` in the background; files only go to the Recycle Bin or trash."""
        management = self._services.management
        name = configuration.name

        def done(result: DeletedServer) -> None:
            kind = "kept" if result.files is None else result.files.kind
            location = "" if result.files is None else result.files.location
            self.message.emit(UserMessage(f"delete.done.{kind}", {"name": name, "location": location}))
            self.changed.emit(None)

        self._run(lambda: management.delete_server(configuration.server_id, remove_files=remove_files), done)

    # --- folder import (M2-GUI-05) ----------------------------------------------------------------

    def inspect_folder(self, folder: str) -> FolderContents | UserMessage:
        """Describe ``folder`` for the import dialog, or return why it cannot be used."""
        if self._services.adoption is None:
            return UserMessage("errors.unexpected")
        try:
            return self._services.adoption.inspect(folder)
        except Exception as error:
            return describe_error(error)

    def adopt(self, folder: str, *, server_id: str, jar_file: str, memory_mb: int) -> None:
        """Import ``folder`` in the background, reporting copy progress."""
        adoption = self._services.adoption
        if adoption is None:
            return
        relay = self._progress_relay

        def work() -> ServerConfiguration:
            return adoption.adopt(
                folder, server_id=server_id, jar_file=jar_file, memory_mb=memory_mb, progress=relay.report
            )

        def done(created: ServerConfiguration) -> None:
            self.message.emit(UserMessage("adopt.done", {"server_id": created.server_id}))
            self.changed.emit(created.server_id)

        self._run(work, done)

    # --- legacy import (M2-GUI-02) ----------------------------------------------------------------

    def pending_legacy_servers(self) -> tuple[str, ...]:
        """Return MCServer 0.9.1 servers not imported yet (none if the legacy list cannot be read)."""
        try:
            return self._services.management.pending_legacy_servers()
        except Exception:
            _logger.warning("Could not read the MCServer 0.9.1 server list.", exc_info=True)
            return ()

    def should_offer_legacy_import(self) -> bool:
        """Return whether the one-time import offer should be shown now."""
        settings = self._services.settings
        if settings is not None and settings.current.legacy_import_offered:
            return False
        return bool(self.pending_legacy_servers())

    def mark_legacy_import_offered(self) -> None:
        """Remember that the offer was shown, so it is never repeated automatically."""
        settings = self._services.settings
        if settings is None or settings.current.legacy_import_offered:
            return
        try:
            settings.update(legacy_import_offered=True)
        except Exception:
            _logger.warning("Could not save that the import was offered.", exc_info=True)

    def import_legacy(self) -> None:
        """Import MCServer 0.9.1 servers in the background (safe to repeat)."""
        management = self._services.management

        def done(result: LegacyImportResult) -> None:
            self.legacy_imported.emit(result)
            self.changed.emit(None)

        self._run(management.import_legacy_servers, done)

    # --- settings (M2-GUI-01) ---------------------------------------------------------------------

    def update_settings(self, **changes: object) -> UserMessage | None:
        """Store changed settings; return an error message, or ``None`` on success."""
        settings = self._services.settings
        if settings is None:
            return UserMessage("errors.unexpected")
        try:
            settings.update(**changes)
        except Exception as error:
            return describe_error(error)
        self.message.emit(UserMessage("settings.saved"))
        return None

    # --- helpers ----------------------------------------------------------------------------------

    def _run(self, work, on_success) -> None:  # type: ignore[no-untyped-def]
        if self._busy:
            return
        self._set_busy(True)

        def succeeded(result: object) -> None:
            self._set_busy(False)
            on_success(result)

        def failed(error: BaseException) -> None:
            self._set_busy(False)
            _logger.error("Management operation failed:\n%s", describe_error(error).details)
            self.failed.emit(describe_error(error))

        self._runner.run(work, succeeded, failed)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.busy_changed.emit(busy)


class _ProgressRelay(QObject):
    """Carries copy progress from a worker thread to the GUI thread."""

    progress = Signal(int, int)

    def report(self, done: int, total: int) -> None:
        self.progress.emit(done, total)


__all__ = ["ManagementController"]
