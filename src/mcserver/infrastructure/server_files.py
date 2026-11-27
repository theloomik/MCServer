"""Local filesystem adapter that prepares server directories and JAR files."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from mcserver.application.errors import (
    InvalidSourceJar,
    ServerDirectoryAlreadyExists,
    ServerFilesystemError,
    ServerJarAlreadyExists,
    UnsafeServerPath,
)
from mcserver.domain.server_configuration import is_safe_name

EULA_FILE = "eula.txt"
_EULA_CONTENT = "# Accepted by the user in MCServer (https://aka.ms/MinecraftEULA)\neula=true\n"


def eula_file_accepted(server_directory: Path) -> bool:
    """Return whether ``server_directory/eula.txt`` contains an ``eula=true`` line."""
    try:
        text = (server_directory / EULA_FILE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() == "eula" and value.strip().lower() == "true":
            return True
    return False


def write_eula_file(server_directory: Path, label: str) -> None:
    """Atomically write ``eula=true`` into ``server_directory`` (temporary file + ``os.replace``)."""
    target = server_directory / EULA_FILE
    temporary = server_directory / f".{EULA_FILE}.tmp"
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(_EULA_CONTENT)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ServerFilesystemError(f"Could not write '{label}/{EULA_FILE}': {error}") from error


class LocalServerFilesystem:
    """Implement ``ServerProvisioningFilesystem`` inside one servers root.

    Safety rules:

    * names must be single safe path segments (the domain rule for
      configuration names), so absolute paths and ``..`` are rejected;
    * a target must resolve to a direct child of the resolved servers root, and
      server directories that are symbolic links are refused, so nothing is
      written outside the root;
    * directories and files are created exclusively (``mkdir`` without
      ``exist_ok``, ``open(..., "xb")``), so existing data is never overwritten,
      even when another program creates the same name concurrently;
    * cleanup removes only what this adapter just created: a partial JAR via
      ``unlink`` and a server directory via ``rmdir``, which refuses to delete
      a directory that is not empty.
    """

    def __init__(self, servers_directory: Path) -> None:
        """Manage server files inside ``servers_directory``."""
        self._servers_directory = servers_directory.resolve()

    def check_source_jar(self, source_jar: str) -> None:
        """Require an existing regular file with a ``.jar`` extension."""
        self._source_path(source_jar)

    def create_directory(self, directory: str) -> None:
        """Create a new empty server directory directly inside the servers root."""
        path = self._server_directory(directory)
        try:
            self._servers_directory.mkdir(parents=True, exist_ok=True)
            path.mkdir()
        except FileExistsError:
            # Also covers a dangling symbolic link with this name.
            raise ServerDirectoryAlreadyExists(directory) from None
        except OSError as error:
            raise ServerFilesystemError(f"Could not create server directory '{directory}': {error}") from error
        try:
            self._require_inside_root(path, directory)
        except UnsafeServerPath:
            self.remove_created_directory(directory)
            raise

    def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
        """Copy the source JAR into the server directory under ``jar_file``, never overwriting."""
        source = self._source_path(source_jar)
        target_directory = self._server_directory(directory)
        if not is_safe_name(jar_file) or not jar_file.lower().endswith(".jar"):
            raise UnsafeServerPath(f"'{jar_file}' is not a safe JAR file name.")
        if target_directory.is_symlink() or not target_directory.is_dir():
            raise UnsafeServerPath(f"Server directory '{directory}' is missing or is a symbolic link.")
        self._require_inside_root(target_directory, directory)
        destination = target_directory / jar_file
        relative = f"{directory}/{jar_file}"

        try:
            source_file = source.open("rb")
        except FileNotFoundError:
            raise InvalidSourceJar(source_jar, "the file no longer exists") from None
        except OSError as error:
            raise ServerFilesystemError(f"Could not read '{source_jar}': {error}") from error

        with source_file:
            try:
                destination_file = destination.open("xb")
            except FileExistsError:
                raise ServerJarAlreadyExists(directory, jar_file) from None
            except OSError as error:
                raise ServerFilesystemError(f"Could not create '{relative}': {error}") from error
            try:
                with destination_file:
                    shutil.copyfileobj(source_file, destination_file)
                    destination_file.flush()
                    os.fsync(destination_file.fileno())
            except OSError as error:
                self._remove_partial_file(destination, relative, error)
                raise ServerFilesystemError(f"Could not copy the JAR to '{relative}': {error}") from error

    def remove_created_directory(self, directory: str) -> None:
        """Remove an empty server directory; a non-empty one is left in place and reported."""
        path = self._server_directory(directory)
        try:
            path.rmdir()
        except FileNotFoundError:
            return
        except OSError as error:
            raise ServerFilesystemError(
                f"Could not remove server directory '{directory}': {error}", leftovers=(directory,)
            ) from error

    def accept_eula(self, directory: str) -> None:
        """Write ``eula=true`` through a temporary file and an atomic replace."""
        target_directory = self._existing_server_directory(directory)
        write_eula_file(target_directory, directory)

    def eula_accepted(self, directory: str) -> bool:
        """Return whether ``eula.txt`` in the server directory says ``eula=true``."""
        return eula_file_accepted(self._server_directory(directory))

    def remove_eula(self, directory: str) -> None:
        """Delete ``eula.txt`` (used only to undo ``accept_eula`` during a failed provisioning)."""
        path = self._server_directory(directory) / EULA_FILE
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise ServerFilesystemError(
                f"Could not remove '{directory}/{EULA_FILE}': {error}", leftovers=(f"{directory}/{EULA_FILE}",)
            ) from error

    def _existing_server_directory(self, directory: str) -> Path:
        """Return a server directory that exists, is not a link and lies directly inside the root."""
        path = self._server_directory(directory)
        if path.is_symlink() or not path.is_dir():
            raise UnsafeServerPath(f"Server directory '{directory}' is missing or is a symbolic link.")
        self._require_inside_root(path, directory)
        return path

    @staticmethod
    def _remove_partial_file(destination: Path, relative: str, cause: OSError) -> None:
        """Delete a partially written JAR created by this adapter, reporting it if that fails."""
        try:
            destination.unlink(missing_ok=True)
        except OSError as cleanup_error:
            raise ServerFilesystemError(
                f"Could not copy the JAR to '{relative}' ({cause}) and could not remove the partial file: "
                f"{cleanup_error}",
                leftovers=(relative,),
            ) from cleanup_error

    def _server_directory(self, directory: str) -> Path:
        """Return the absolute path for a server directory name, rejecting unsafe names."""
        if not is_safe_name(directory):
            raise UnsafeServerPath(f"'{directory}' is not a safe server directory name.")
        return self._servers_directory / directory

    def _require_inside_root(self, path: Path, directory: str) -> None:
        """Refuse a server directory that resolves anywhere but directly inside the root."""
        if path.resolve().parent != self._servers_directory:
            raise UnsafeServerPath(f"Server directory '{directory}' resolves outside the servers root.")

    @staticmethod
    def _source_path(source_jar: str) -> Path:
        """Validate the user-selected source JAR and return its path."""
        if not source_jar:
            raise InvalidSourceJar(source_jar, "no file was selected")
        path = Path(source_jar)
        if path.suffix.lower() != ".jar":
            raise InvalidSourceJar(source_jar, "the file name does not end with .jar")
        try:
            if not path.exists():
                raise InvalidSourceJar(source_jar, "the file does not exist")
            if not path.is_file():
                raise InvalidSourceJar(source_jar, "the path is not a regular file")
        except OSError as error:
            raise InvalidSourceJar(source_jar, f"the file cannot be accessed: {error}") from error
        return path
