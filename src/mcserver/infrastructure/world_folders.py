"""World folders inside a server folder: find, copy in, archive out, move away (M3-BE-07)."""

from __future__ import annotations

import logging
import os
import shutil
import zipfile
from pathlib import Path, PurePosixPath

from mcserver.application.ports import RemovedServerFiles
from mcserver.application.worlds import DIMENSION_SUFFIXES, WorldFolder, WorldProgress
from mcserver.domain.server_configuration import is_safe_name
from mcserver.infrastructure.recycle_bin import RecycleBinServerFilesRemover
from mcserver.infrastructure.server_configuration import world_folder_locked

_logger = logging.getLogger(__name__)

LEVEL_FILE = "level.dat"
_CHUNK = 1024 * 1024
_SKIPPED_FILES = frozenset({"session.lock"})
_STAGING_PREFIX = ".world-import-"


def _files(folder: Path) -> list[tuple[Path, PurePosixPath]]:
    """Return the regular files below ``folder`` with their relative POSIX names (links are skipped)."""
    found: list[tuple[Path, PurePosixPath]] = []
    for base, folders, names in os.walk(folder, followlinks=False):
        folders[:] = [name for name in folders if not (Path(base) / name).is_symlink()]
        for name in names:
            path = Path(base) / name
            if name in _SKIPPED_FILES or path.is_symlink() or not path.is_file():
                continue
            found.append((path, PurePosixPath(path.relative_to(folder).as_posix())))
    return found


def _size(folder: Path) -> int:
    total = 0
    for path, _name in _files(folder):
        try:
            total += path.stat().st_size
        except OSError:
            continue
    return total


class LocalWorldStore:
    """Implement ``WorldStore`` on the local disk under the servers root."""

    def __init__(self, servers_directory: Path, remover: RecycleBinServerFilesRemover | None = None) -> None:
        """Work inside ``servers_directory``; removed worlds go through ``remover``."""
        self._root = servers_directory.resolve()
        self._remover = remover or RecycleBinServerFilesRemover(self._root)

    # --- reading -------------------------------------------------------------------------------

    def list_worlds(self, directory: str) -> tuple[WorldFolder, ...]:
        """Return each folder with ``level.dat``; ``<name>_nether`` / ``<name>_the_end`` join ``<name>``."""
        server = self._server_folder(directory)
        if not server.is_dir():
            return ()
        levels = sorted(
            child.name
            for child in server.iterdir()
            if child.is_dir()
            and not child.is_symlink()
            and not child.name.startswith(".")
            and (child / LEVEL_FILE).is_file()
        )
        names = set(levels)
        groups: dict[str, list[str]] = {}
        for name in levels:
            base = next((name[: -len(suffix)] for suffix in DIMENSION_SUFFIXES if name.endswith(suffix)), None)
            owner = base if base is not None and base in names else name
            groups.setdefault(owner, []).append(name)
        worlds: list[WorldFolder] = []
        for name, folders in groups.items():
            ordered = tuple(sorted(folders, key=lambda folder: (folder != name, folder)))
            modified = max((server / folder / LEVEL_FILE).stat().st_mtime for folder in ordered)
            worlds.append(WorldFolder(name, ordered, sum(_size(server / folder) for folder in ordered), modified))
        return tuple(worlds)

    def folder_exists(self, directory: str, name: str) -> bool:
        """Return whether anything named ``name`` exists in the server folder."""
        return (self._server_folder(directory) / name).exists()

    # --- import --------------------------------------------------------------------------------

    def import_world(self, directory: str, source: str, name: str, progress: WorldProgress | None) -> None:
        """Copy a world from a folder or ZIP archive; it appears only once it is complete."""
        server = self._server_folder(directory)
        target = server / name
        if not is_safe_name(name) or target.exists():
            raise ValueError(f"'{name}' cannot be used as the new world folder")
        source_path = Path(source)
        staging = server / f"{_STAGING_PREFIX}{name}"
        if staging.exists():
            self._remover.remove_path(staging)  # left over from an interrupted import
        try:
            if source_path.is_dir():
                self._copy_folder(source_path, staging, progress)
            elif source_path.is_file() and zipfile.is_zipfile(source_path):
                self._extract_world(source_path, staging, progress)
            else:
                raise ValueError("it is neither a folder nor a ZIP archive")
            os.replace(staging, target)
        except BaseException:
            self._discard(staging)
            raise

    def _discard(self, staging: Path) -> None:
        """Move an incomplete copy out of the way (Recycle Bin or trash), keeping the original error."""
        if not staging.exists():
            return
        try:
            self._remover.remove_path(staging)
        except Exception:  # the import already failed; its own error is what the user needs to see
            _logger.exception("Could not move the incomplete world copy %s away.", staging)

    def _copy_folder(self, source: Path, staging: Path, progress: WorldProgress | None) -> None:
        world = self._world_root(source)
        resolved = world.resolve()
        server = staging.parent.resolve()
        if server in (resolved, *resolved.parents) or resolved in server.parents:
            raise ValueError("the world is already inside this server folder")
        if world_folder_locked(world):
            raise ValueError("a running Minecraft server is using this world; stop it first")
        files = _files(world)
        total = sum(path.stat().st_size for path, _name in files)
        done = 0
        staging.mkdir(parents=True)
        for path, name in files:
            destination = staging.joinpath(*name.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with path.open("rb") as reader, destination.open("xb") as writer:
                while chunk := reader.read(_CHUNK):
                    writer.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)
            shutil.copystat(path, destination)

    @staticmethod
    def _world_root(source: Path) -> Path:
        """Return ``source`` or its only sub-folder holding ``level.dat`` (archives often wrap the world)."""
        if (source / LEVEL_FILE).is_file():
            return source
        candidates = [child for child in source.iterdir() if child.is_dir() and (child / LEVEL_FILE).is_file()]
        if len(candidates) == 1:
            return candidates[0]
        raise ValueError("no level.dat was found" if not candidates else "it contains several worlds")

    @staticmethod
    def _extract_world(archive: Path, staging: Path, progress: WorldProgress | None) -> None:
        with zipfile.ZipFile(archive) as zip_file:
            members = zip_file.infolist()
            for member in members:
                name = PurePosixPath(member.filename)
                if name.is_absolute() or ".." in name.parts or ":" in member.filename or "\\" in member.filename:
                    raise ValueError(f"unsafe path in archive: {member.filename}")
            levels = [
                PurePosixPath(member.filename).parent
                for member in members
                if PurePosixPath(member.filename).name == LEVEL_FILE
            ]
            if not levels:
                raise ValueError("no level.dat was found")
            depth = min(len(level.parts) for level in levels)
            roots = {level for level in levels if len(level.parts) == depth}
            if len(roots) != 1:
                raise ValueError("it contains several worlds")
            root = roots.pop()
            chosen = [
                member
                for member in members
                if not member.is_dir()
                and PurePosixPath(member.filename).is_relative_to(root)
                and PurePosixPath(member.filename).name not in _SKIPPED_FILES
            ]
            total = sum(member.file_size for member in chosen)
            done = 0
            staging.mkdir(parents=True)
            for member in chosen:
                relative = PurePosixPath(member.filename).relative_to(root)
                destination = staging.joinpath(*relative.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with zip_file.open(member) as reader, destination.open("xb") as writer:  # CRC checked on read
                    while chunk := reader.read(_CHUNK):
                        writer.write(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress(done, total)

    # --- export --------------------------------------------------------------------------------

    def export_world(
        self, directory: str, folders: tuple[str, ...], target: str, progress: WorldProgress | None
    ) -> None:
        """Archive ``folders`` (each as a top-level folder) into ``target``; written as ``.partial`` first."""
        server = self._server_folder(directory)
        files = [(path, PurePosixPath(folder) / name) for folder in folders for path, name in _files(server / folder)]
        total = sum(path.stat().st_size for path, _name in files)
        destination = Path(target)
        partial = destination.with_name(destination.name + ".partial")
        done = 0
        try:
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
                for path, name in files:
                    info = zipfile.ZipInfo.from_file(path, str(name))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    with path.open("rb") as reader, zip_file.open(info, "w", force_zip64=True) as writer:
                        while chunk := reader.read(_CHUNK):
                            writer.write(chunk)
                            done += len(chunk)
                            if progress is not None:
                                progress(done, total)
            os.replace(partial, destination)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    # --- remove --------------------------------------------------------------------------------

    def remove_world(self, directory: str, folders: tuple[str, ...]) -> tuple[RemovedServerFiles, ...]:
        """Move each folder to the Recycle Bin, or into the trash folder; nothing is deleted permanently."""
        server = self._server_folder(directory)
        return tuple(self._remover.remove_path(server / folder) for folder in folders)

    def _server_folder(self, directory: str) -> Path:
        if not is_safe_name(directory):
            raise ValueError(f"'{directory}' is not a server folder name")
        return self._root / directory
