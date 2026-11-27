"""Inspect and copy existing server folders for adoption (M2-BE-04, ADR 0004 amendment).

Rules:

* the source folder is only read, never moved or changed;
* a folder whose world is in use (``session.lock`` held) is not copied;
* the copy goes into a new folder created exclusively inside the servers root;
  existing files are never overwritten;
* undoing a copy removes only the files and folders this adapter created in
  this process (no recursive delete); anything else is reported as leftover.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from mcserver.application.errors import (
    InvalidSourceJar,
    ServerDirectoryAlreadyExists,
    ServerFilesystemError,
    ServerWorldInUse,
    UnsafeServerPath,
)
from mcserver.application.server_adoption import CopyProgress, FolderContents
from mcserver.domain.server_configuration import is_safe_name
from mcserver.infrastructure.server_configuration import locked_world
from mcserver.infrastructure.server_files import eula_file_accepted
from mcserver.infrastructure.session_markers import MARKER_DIRECTORY

_CHUNK = 1024 * 1024


class LocalServerFolderAdoption:
    """Implement ``ServerAdoptionFilesystem`` for one servers root."""

    def __init__(self, servers_directory: Path) -> None:
        """Copy folders into ``servers_directory``."""
        self._root = servers_directory.resolve()
        self._created: dict[str, list[Path]] = {}

    def inspect_folder(self, folder: str) -> FolderContents:
        """Describe ``folder``: whether it is inside the root, its JAR files and EULA state."""
        path = Path(folder)
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_dir():
                raise InvalidSourceJar(folder, "the selected path is not a folder")
            jars = tuple(
                sorted(child.name for child in resolved.iterdir() if child.is_file() and child.suffix.lower() == ".jar")
            )
        except OSError as error:
            raise InvalidSourceJar(folder, f"the folder cannot be read: {error}") from error
        return FolderContents(
            folder=str(resolved),
            inside_root=resolved.parent == self._root and not path.is_symlink(),
            directory=resolved.name,
            jar_files=jars,
            eula_accepted=eula_file_accepted(resolved),
        )

    def copy_folder(self, folder: str, directory: str, progress: CopyProgress | None = None) -> None:
        """Copy ``folder`` into ``<root>/<directory>``; refuse a running world and an existing target."""
        source = Path(folder).resolve()
        if not is_safe_name(directory):
            raise UnsafeServerPath(f"'{directory}' is not a safe server directory name.")
        world = locked_world(source)
        if world is not None:
            raise ServerWorldInUse(directory, world)
        target = self._root / directory
        if source == target or target in source.parents or source in target.parents:
            raise UnsafeServerPath("The folder cannot be copied into itself.")
        files: list[tuple[Path, Path]] = []
        folders_to_create: list[Path] = []
        for base, folders, names in os.walk(source, followlinks=False):
            # Never copy MCServer's own session marker folder.
            folders[:] = [name for name in folders if name != MARKER_DIRECTORY]
            folders_to_create.extend(Path(base).relative_to(source) / name for name in folders)
            for name in names:
                path = Path(base) / name
                if not path.is_symlink():
                    files.append((path, path.relative_to(source)))
        total = sum(_size(path) for path, _relative in files)
        created: list[Path] = []
        self._created[directory] = created
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            target.mkdir()
        except FileExistsError:
            raise ServerDirectoryAlreadyExists(directory) from None
        except OSError as error:
            raise ServerFilesystemError(f"Could not create '{directory}': {error}") from error
        created.append(target)
        done = 0
        try:
            for relative_folder in folders_to_create:  # keeps empty folders such as plugins/
                self._make_parents(target / relative_folder, target, created)
            for source_file, relative in files:
                destination = target / relative
                self._make_parents(destination.parent, target, created)
                with source_file.open("rb") as reader, destination.open("xb") as writer:
                    created.append(destination)
                    while chunk := reader.read(_CHUNK):
                        writer.write(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress(done, total)
                shutil.copystat(source_file, destination)
        except OSError as error:
            raise ServerFilesystemError(f"Could not copy the folder into '{directory}': {error}") from error

    def remove_copied_folder(self, directory: str) -> None:
        """Remove what ``copy_folder`` created for ``directory``, newest first; report what remains."""
        leftovers: list[str] = []
        for path in reversed(self._created.pop(directory, [])):
            try:
                path.rmdir() if path.is_dir() and not path.is_symlink() else path.unlink(missing_ok=True)
            except OSError:
                leftovers.append(str(path.relative_to(self._root)))
        if leftovers:
            raise ServerFilesystemError(f"Could not remove the copy of '{directory}'.", tuple(leftovers))

    @staticmethod
    def _make_parents(folder: Path, target: Path, created: list[Path]) -> None:
        missing: list[Path] = []
        current = folder
        while current != target and not current.exists():
            missing.append(current)
            current = current.parent
        for path in reversed(missing):
            path.mkdir()
            created.append(path)


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0
