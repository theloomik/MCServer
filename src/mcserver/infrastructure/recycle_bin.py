"""Move a server folder to the Windows Recycle Bin, or to ``<root>/.trash`` as a fallback (M2-BE-03).

Nothing is ever deleted permanently:

* ``SHFileOperationW`` is called with ``FOF_ALLOWUNDO`` (Recycle Bin) and
  ``FOF_WANTNUKEWARNING``: on a drive without a Recycle Bin, Windows asks the
  user before destroying anything, and a refusal counts as a failure;
* if the Recycle Bin cannot be used, the folder is renamed into ``.trash``
  inside the servers root (same drive, so a rename, not a copy);
* if both fail, ``ServerFilesRemovalFailed`` is raised and nothing changed.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from collections.abc import Callable
from ctypes import wintypes
from pathlib import Path

from mcserver.application.errors import ServerFilesRemovalFailed
from mcserver.application.ports import RemovedServerFiles
from mcserver.domain.server_configuration import is_safe_name

TRASH_DIRECTORY = ".trash"

_FO_DELETE = 3
_FOF_SILENT = 0x0004
_FOF_NOCONFIRMATION = 0x0010
_FOF_ALLOWUNDO = 0x0040
_FOF_NOERRORUI = 0x0400
_FOF_WANTNUKEWARNING = 0x4000


class _ShFileOperation(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


def send_to_recycle_bin(path: Path) -> None:
    """Move ``path`` to the Recycle Bin; raise ``OSError`` if it was not moved there."""
    if sys.platform != "win32":
        raise OSError("The Recycle Bin is only available on Windows.")
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.SHFileOperationW.argtypes = (ctypes.POINTER(_ShFileOperation),)
    shell32.SHFileOperationW.restype = ctypes.c_int
    source = ctypes.create_unicode_buffer(str(path) + "\0")  # double-null-terminated list
    operation = _ShFileOperation()
    operation.wFunc = _FO_DELETE
    operation.pFrom = ctypes.cast(source, ctypes.c_wchar_p)
    operation.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_WANTNUKEWARNING | _FOF_SILENT | _FOF_NOERRORUI
    result = shell32.SHFileOperationW(ctypes.byref(operation))
    if result != 0:
        raise OSError(f"SHFileOperationW failed with code {result:#x}")
    if operation.fAnyOperationsAborted:
        raise OSError("moving to the Recycle Bin was cancelled")
    if path.exists():
        raise OSError("the folder is still there after moving it to the Recycle Bin")


class RecycleBinServerFilesRemover:
    """Implement ``ServerFilesRemover`` for folders directly inside the servers root."""

    def __init__(
        self,
        servers_directory: Path,
        recycle: Callable[[Path], None] = send_to_recycle_bin,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Remove folders inside ``servers_directory``; ``recycle`` and ``clock`` are injectable for tests."""
        self._root = servers_directory.resolve()
        self._recycle = recycle
        self._clock = clock

    def remove_server_files(self, directory: str) -> RemovedServerFiles:
        """Send the folder to the Recycle Bin, else move it into ``.trash``; never delete it."""
        path = self._server_folder(directory)
        if not path.exists():
            return RemovedServerFiles("missing", str(path))
        recycle_error: OSError | None = None
        try:
            self._recycle(path)
        except OSError as error:
            recycle_error = error
        else:
            return RemovedServerFiles("recycle_bin", str(path))
        if path.exists():
            target = self._root / TRASH_DIRECTORY / f"{directory}-{int(self._clock())}"
            try:
                target.parent.mkdir(exist_ok=True)
                os.replace(path, target)
            except OSError as error:
                raise ServerFilesRemovalFailed(
                    directory, f"Recycle Bin: {recycle_error}; trash folder: {error}"
                ) from error
            return RemovedServerFiles("trash", str(target))
        # The Recycle Bin call reported an error although the folder is gone (it was recycled).
        return RemovedServerFiles("recycle_bin", str(path))

    def _server_folder(self, directory: str) -> Path:
        if not is_safe_name(directory) or directory == TRASH_DIRECTORY:
            raise ServerFilesRemovalFailed(directory, "not a server folder name")
        path = self._root / directory
        if path.is_symlink():
            raise ServerFilesRemovalFailed(directory, "the folder is a link; it was left in place")
        if path.exists() and (not path.is_dir() or path.resolve().parent != self._root):
            raise ServerFilesRemovalFailed(directory, "not a folder inside the servers folder")
        return path
