"""Zip archives of server folders with JSON metadata (M3-BE-03, ADR 0008).

Layout: ``<servers root>/.backups/<server_id>/<backup_id>.zip`` plus
``<backup_id>.json``.

* **What is archived:** the whole server folder except files the server can
  recreate or that MCServer owns: ``cache``, ``libraries``, ``versions``,
  ``logs``, ``crash-reports``, ``debug``, ``.mcserver`` and every
  ``session.lock``.
* **Create:** checks free disk space, writes ``<id>.zip.partial`` and renames
  it when complete; a failure removes only that partial file.
* **Restore:** extracts into a staging folder (rejecting paths that escape it,
  verifying every file's CRC), then swaps: the current folder is renamed aside,
  the staging folder takes its place, the excluded items (logs, libraries…) are
  moved back in, and the replaced folder goes to the Recycle Bin. Until the swap
  the original folder is untouched; a crash in between is repaired by
  ``recover_interrupted_restores``.
* **Delete:** archives go to the Recycle Bin (or the trash folder), like server
  folders. Server files are never deleted permanently.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import zipfile
import zlib
from datetime import datetime
from pathlib import Path, PurePosixPath

from mcserver.application.backup_schedule import BackupSchedule, InvalidBackupSchedule
from mcserver.application.backups import BackupFailed, BackupInfo, BackupKind, BackupProgress
from mcserver.application.ports import RemovedServerFiles
from mcserver.domain.server_configuration import is_safe_name
from mcserver.infrastructure.recycle_bin import RecycleBinServerFilesRemover

SCHEDULE_FILE_NAME = "schedule.json"

BACKUPS_DIRECTORY = ".backups"
EXCLUDED_TOP_LEVEL = frozenset({"cache", "libraries", "versions", "logs", "crash-reports", "debug", ".mcserver"})
EXCLUDED_NAMES = frozenset({"session.lock"})
_STAGING_PREFIX = ".restore-"
_OLD_PREFIX = ".restore-old-"
_CHUNK = 1024 * 1024
_FREE_SPACE_MARGIN = 64 * 1024 * 1024

_logger = logging.getLogger(__name__)


class ZipBackupStore:
    """Implement ``BackupStore`` inside one servers root."""

    def __init__(self, servers_directory: Path, remover: RecycleBinServerFilesRemover | None = None) -> None:
        """Keep archives under ``<servers_directory>/.backups``."""
        self._root = servers_directory.resolve()
        self._remover = remover or RecycleBinServerFilesRemover(self._root)

    # --- listing -------------------------------------------------------------------------------

    def list_backups(self, server_id: str) -> tuple[BackupInfo, ...]:
        """Return backups with readable metadata whose archive exists, newest first."""
        folder = self._backup_folder(server_id)
        found: list[BackupInfo] = []
        for metadata in folder.glob("*.json") if folder.is_dir() else ():
            if metadata.name == SCHEDULE_FILE_NAME:
                continue
            try:
                info = _info_from(json.loads(metadata.read_text(encoding="utf-8")))
            except (OSError, ValueError, KeyError, TypeError):
                _logger.warning("Ignoring unreadable backup metadata %s.", metadata)
                continue
            if info.server_id == server_id and (folder / f"{info.backup_id}.zip").is_file():
                found.append(info)
        return tuple(sorted(found, key=lambda info: (info.created_at, info.backup_id), reverse=True))

    # --- create --------------------------------------------------------------------------------

    def create_backup(
        self,
        server_id: str,
        directory: str,
        kind: BackupKind,
        note: str,
        online: bool,
        created_at: datetime,
        progress: BackupProgress | None,
    ) -> BackupInfo:
        """Archive the server folder; on any failure nothing is left behind."""
        source = self._server_folder(directory)
        if not source.is_dir():
            raise BackupFailed(server_id, "the server folder does not exist")
        files = list(_backup_files(source))
        total = sum(size for _path, _name, size in files)
        folder = self._backup_folder(server_id)
        folder.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(folder).free
        if free < total + _FREE_SPACE_MARGIN:
            raise BackupFailed(
                server_id, f"not enough free disk space ({free // 2**20} MB free, about {total // 2**20} MB needed)"
            )
        backup_id = self._new_id(folder, created_at, kind)
        partial = folder / f"{backup_id}.zip.partial"
        archive = folder / f"{backup_id}.zip"
        done = 0
        try:
            with zipfile.ZipFile(partial, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zip_file:
                for path, name, _size in files:
                    try:
                        with (
                            path.open("rb") as reader,
                            zip_file.open(_zip_info(path, name), "w", force_zip64=True) as writer,
                        ):
                            while chunk := reader.read(_CHUNK):
                                writer.write(chunk)
                                done += len(chunk)
                                if progress is not None:
                                    progress(done, total)
                    except FileNotFoundError:
                        continue  # removed while archiving (temporary files)
            os.replace(partial, archive)
        except (OSError, zipfile.BadZipFile) as error:
            partial.unlink(missing_ok=True)
            raise BackupFailed(server_id, f"the archive could not be written: {error}") from error
        except BaseException:
            partial.unlink(missing_ok=True)  # cancelled: no half-written archive is kept
            raise
        info = BackupInfo(
            backup_id, server_id, created_at.isoformat(timespec="seconds"), archive.stat().st_size, kind, note, online
        )
        try:
            _write_json(folder / f"{backup_id}.json", _info_to(info, directory))
        except OSError as error:
            archive.unlink(missing_ok=True)
            raise BackupFailed(server_id, f"the backup description could not be written: {error}") from error
        return info

    # --- restore -------------------------------------------------------------------------------

    def restore_backup(self, server_id: str, directory: str, backup_id: str, progress: BackupProgress | None) -> None:
        """Replace the server folder with the archive (see the module docstring for the safety steps)."""
        archive = self._archive(server_id, backup_id)
        target = self._server_folder(directory)
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        staging = self._root / f"{_STAGING_PREFIX}{directory}-{stamp}"
        try:
            staging.mkdir()
            _extract(archive, staging, progress)
        except (OSError, zipfile.BadZipFile, ValueError, zlib.error) as error:
            shutil.rmtree(staging, ignore_errors=True)  # only the copy extracted by this call
            raise BackupFailed(server_id, f"the backup could not be read: {error}") from error
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)  # cancelled before the swap: the server folder is untouched
            raise
        old = self._root / f"{_OLD_PREFIX}{directory}-{stamp}"
        try:
            if target.exists():
                os.replace(target, old)
            os.replace(staging, target)
        except OSError as error:
            if old.exists() and not target.exists():
                os.replace(old, target)
            shutil.rmtree(staging, ignore_errors=True)
            raise BackupFailed(server_id, f"the server folder could not be replaced: {error}") from error
        self._finish_swap(old, target)

    def _finish_swap(self, old: Path, target: Path) -> None:
        """Move the excluded items back from the replaced folder, then recycle what remains of it."""
        if not old.exists():
            return
        for name in EXCLUDED_TOP_LEVEL:
            if (old / name).exists() and not (target / name).exists():
                try:
                    os.replace(old / name, target / name)
                except OSError:
                    _logger.warning("Could not move %s back after a restore.", old / name)
        try:
            self._remover.remove_path(old)
        except Exception:
            _logger.warning("The replaced folder %s was kept; delete it manually when no longer needed.", old)

    def recover_interrupted_restores(self) -> tuple[str, ...]:
        """Put back an original folder a crash left aside, finish half-done swaps, drop staging copies."""
        repaired: list[str] = []
        if not self._root.is_dir():
            return ()
        for old in sorted(self._root.glob(f"{_OLD_PREFIX}*")):
            directory = old.name[len(_OLD_PREFIX) :].rsplit("-", 1)[0]
            if not is_safe_name(directory):
                continue
            target = self._root / directory
            if not target.exists():
                os.replace(old, target)  # the swap never happened: the original comes back
            else:
                self._finish_swap(old, target)  # the swap happened: finish it
            repaired.append(directory)
        for staging in self._root.glob(f"{_STAGING_PREFIX}*"):
            if not staging.name.startswith(_OLD_PREFIX):
                shutil.rmtree(staging, ignore_errors=True)  # an extracted copy that was never swapped in
        return tuple(repaired)

    # --- schedule ------------------------------------------------------------------------------

    def load_schedule(self, server_id: str) -> BackupSchedule:
        """Return the stored schedule; a missing or damaged file means \"off\" (logged)."""
        path = self._backup_folder(server_id) / SCHEDULE_FILE_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BackupSchedule(enabled=data["enabled"], interval_hours=data["interval_hours"], keep=data["keep"])
        except FileNotFoundError:
            return BackupSchedule()
        except (OSError, ValueError, KeyError, TypeError, InvalidBackupSchedule):
            _logger.warning("Ignoring the unreadable backup schedule %s.", path)
            return BackupSchedule()

    def save_schedule(self, server_id: str, schedule: BackupSchedule) -> None:
        """Store ``schedule`` next to the server's backups."""
        folder = self._backup_folder(server_id)
        data: dict[str, object] = {
            "format_version": 1,
            "enabled": schedule.enabled,
            "interval_hours": schedule.interval_hours,
            "keep": schedule.keep,
        }
        try:
            folder.mkdir(parents=True, exist_ok=True)
            _write_json(folder / SCHEDULE_FILE_NAME, data)
        except OSError as error:
            raise BackupFailed(server_id, f"the backup schedule could not be saved: {error}") from error

    # --- delete --------------------------------------------------------------------------------

    def delete_backup(self, server_id: str, backup_id: str) -> RemovedServerFiles:
        """Move the archive and its description to the Recycle Bin (or trash)."""
        archive = self._archive(server_id, backup_id)
        result = self._remover.remove_path(archive)
        metadata = archive.with_suffix(".json")
        if metadata.exists():
            self._remover.remove_path(metadata)
        return result

    # --- helpers -------------------------------------------------------------------------------

    def _backup_folder(self, server_id: str) -> Path:
        if not is_safe_name(server_id):
            raise BackupFailed(server_id, "invalid server identifier")
        return self._root / BACKUPS_DIRECTORY / server_id

    def _server_folder(self, directory: str) -> Path:
        if not is_safe_name(directory):
            raise BackupFailed(directory, "invalid server folder name")
        return self._root / directory

    def _archive(self, server_id: str, backup_id: str) -> Path:
        if not is_safe_name(backup_id):
            raise BackupFailed(server_id, "invalid backup identifier")
        archive = self._backup_folder(server_id) / f"{backup_id}.zip"
        if not archive.is_file():
            raise BackupFailed(server_id, f"the archive {archive.name} is missing")
        return archive

    @staticmethod
    def _new_id(folder: Path, created_at: datetime, kind: BackupKind) -> str:
        base = f"{created_at.strftime('%Y%m%d-%H%M%S')}-{kind.value}"
        candidate, number = base, 2
        while (folder / f"{candidate}.zip").exists() or (folder / f"{candidate}.json").exists():
            candidate, number = f"{base}-{number}", number + 1
        return candidate


def _backup_files(source: Path):  # type: ignore[no-untyped-def]
    """Yield (path, archive name, size) of every file to archive, sorted, skipping exclusions and links."""
    for base, folders, names in os.walk(source, followlinks=False):
        relative = Path(base).relative_to(source)
        if relative == Path("."):
            folders[:] = [name for name in folders if name not in EXCLUDED_TOP_LEVEL]
        folders.sort()
        for name in sorted(names):
            path = Path(base) / name
            if name in EXCLUDED_NAMES or path.is_symlink() or (relative == Path(".") and name in EXCLUDED_TOP_LEVEL):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            yield path, (relative / name).as_posix(), size


def _zip_info(path: Path, name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo.from_file(path, name)
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _extract(archive: Path, staging: Path, progress: BackupProgress | None) -> None:
    """Extract every member into ``staging``; refuse names that would escape it."""
    with zipfile.ZipFile(archive) as zip_file:
        members = zip_file.infolist()
        total = sum(member.file_size for member in members)
        done = 0
        for member in members:
            name = PurePosixPath(member.filename)
            if name.is_absolute() or ".." in name.parts or ":" in member.filename:
                raise ValueError(f"unsafe path in archive: {member.filename}")
            destination = staging.joinpath(*name.parts)
            if member.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(member) as reader, destination.open("xb") as writer:  # CRC is checked on read
                while chunk := reader.read(_CHUNK):
                    writer.write(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total)


def _write_json(path: Path, data: dict[str, object]) -> None:
    temporary = path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _info_to(info: BackupInfo, directory: str) -> dict[str, object]:
    return {
        "format_version": 1,
        "backup_id": info.backup_id,
        "server_id": info.server_id,
        "directory": directory,
        "created_at": info.created_at,
        "size_bytes": info.size_bytes,
        "kind": info.kind.value,
        "note": info.note,
        "online": info.online,
    }


def _info_from(data: dict[str, object]) -> BackupInfo:
    if data.get("format_version") != 1:
        raise ValueError("unsupported backup metadata version")
    size = data["size_bytes"]
    if not isinstance(size, int):
        raise TypeError("size_bytes")
    return BackupInfo(
        backup_id=str(data["backup_id"]),
        server_id=str(data["server_id"]),
        created_at=str(data["created_at"]),
        size_bytes=size,
        kind=BackupKind(str(data["kind"])),
        note=str(data.get("note", "")),
        online=bool(data.get("online", False)),
    )
