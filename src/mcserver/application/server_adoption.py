"""Use case: bring an existing server folder under MCServer's management (M2-BE-04, ADR 0004 amendment)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mcserver.application.errors import InvalidSourceJar, ServerConfigurationAlreadyExists, ServerProvisioningError
from mcserver.application.progress import CancelToken, ProgressReporter, Stage, stage_callback
from mcserver.application.server_management import ServerManagement
from mcserver.domain.server_configuration import ServerConfiguration

CopyProgress = Callable[[int, int], None]
"""Called with (bytes copied, total bytes) while a folder is copied."""


@dataclass(frozen=True, slots=True)
class FolderContents:
    """What an existing server folder contains."""

    folder: str
    """Absolute path of the selected folder."""
    inside_root: bool
    """The folder is directly inside the servers root and can be registered in place."""
    directory: str
    """The folder's own name."""
    jar_files: tuple[str, ...]
    """``.jar`` files directly inside the folder, sorted."""
    eula_accepted: bool


class ServerAdoptionFilesystem(Protocol):
    """File operations for adopting a folder; all failures raise ``ServerProvisioningError`` subclasses.

    ``copy_folder`` never modifies the source and refuses a world that is in
    use (``ServerWorldInUse``). ``remove_copied_folder`` removes only files
    that ``copy_folder`` created in this process and reports the rest as leftovers.
    """

    def inspect_folder(self, folder: str) -> FolderContents:
        """Describe ``folder``; raise ``InvalidSourceJar`` if it is not a readable folder."""

    def copy_folder(self, folder: str, directory: str, progress: CopyProgress | None = None) -> None:
        """Copy ``folder`` into a new ``directory`` inside the servers root (never overwriting)."""

    def remove_copied_folder(self, directory: str) -> None:
        """Undo ``copy_folder`` for ``directory``."""


class ServerAdoption:
    """Register a folder in place (inside the root) or copy it in (outside the root), never moving it.

    The copy is compensated like server creation: if storing the configuration
    fails, the copy is removed again; the source is never touched.
    """

    def __init__(self, management: ServerManagement, filesystem: ServerAdoptionFilesystem) -> None:
        """Store records through ``management`` and handle files through ``filesystem``."""
        self._management = management
        self._filesystem = filesystem

    def inspect(self, folder: str) -> FolderContents:
        """Describe ``folder`` so the GUI can offer its JAR files."""
        return self._filesystem.inspect_folder(folder)

    def adopt(
        self,
        folder: str,
        *,
        server_id: str,
        jar_file: str,
        memory_mb: int,
        display_name: str = "",
        progress: ProgressReporter | None = None,
        cancel: CancelToken | None = None,
    ) -> ServerConfiguration:
        """Make ``folder`` a managed server and return its stored configuration."""
        contents = self._filesystem.inspect_folder(folder)
        if jar_file not in contents.jar_files:
            raise InvalidSourceJar(jar_file, "the JAR is not inside the selected folder")
        if contents.inside_root:
            created = self._management.create_server(
                server_id=server_id, directory=contents.directory, jar_file=jar_file, memory_mb=memory_mb
            )
        else:
            # Validate the record before copying gigabytes of world data.
            ServerConfiguration(server_id, server_id, jar_file, memory_mb, display_name=display_name)
            if any(existing.server_id == server_id for existing in self._management.list_servers()):
                raise ServerConfigurationAlreadyExists(server_id)
            try:
                self._filesystem.copy_folder(folder, server_id, stage_callback(Stage.COPYING, progress, cancel))
            except BaseException:
                # Cancelled or failed half way: remove what this copy created, keep the original error.
                try:
                    self._filesystem.remove_copied_folder(server_id)
                except ServerProvisioningError:
                    pass
                raise
            try:
                created = self._management.create_server(
                    server_id=server_id, directory=server_id, jar_file=jar_file, memory_mb=memory_mb
                )
            except Exception:
                try:
                    self._filesystem.remove_copied_folder(server_id)
                except ServerProvisioningError:
                    pass  # the record error is the one to report; leftovers are in the logs of the adapter
                raise
        if display_name:
            created = self._management.update_server(server_id, display_name=display_name)
        return created
