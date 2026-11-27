"""Orphan protection for server processes with a Windows Job Object (ADR 0006).

Sequence, so Java never runs unguarded:

1. the process is created with ``CREATE_SUSPENDED`` (it exists but has run no code);
2. it is assigned to a job whose limit is ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``;
3. its primary thread is resumed (``subprocess`` closes the thread handle, so the
   thread is found with ``CreateToolhelp32Snapshot``; a new suspended process has
   exactly one thread);
4. if 2 or 3 fails, the never-run process is terminated and the start fails.

Only the server's process tree joins the job, never MCServer itself. When
MCServer ends for any reason, Windows closes the job handle and terminates the
server, so no orphan keeps the port and ``session.lock``. Normal stops never
rely on this: they are graceful. The only remaining gap is MCServer dying
between steps 1 and 2; the child then stays suspended, has run no code and
holds no world lock.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Protocol

from mcserver.application.errors import ProcessGuardUnavailable

CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
"""Java is a console program: without this, MCServer (a window, not a console) would open a console for it."""
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_THREAD_SUSPEND_RESUME = 0x0002
_TH32CS_SNAPTHREAD = 0x00000004
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class JobApi(Protocol):
    """The Win32 operations the guard needs; a fake replaces it in unit tests."""

    def create_kill_on_close_job(self) -> int:
        """Create a job that terminates its processes when its last handle closes."""

    def assign(self, job: int, process_id: int) -> None:
        """Put the process into the job; raise ``OSError`` on failure."""

    def resume_primary_thread(self, process_id: int) -> None:
        """Resume the single thread of a process created suspended; raise ``OSError`` on failure."""

    def terminate(self, process_id: int) -> None:
        """Terminate the process; errors are ignored."""

    def close(self, job: int) -> None:
        """Close the job handle (terminating anything still inside it)."""

    def is_in_job(self, job: int, process_id: int) -> bool:
        """Return whether the process belongs to the job."""


class ProcessGuard(Protocol):
    """Protects one server process from outliving MCServer."""

    @property
    def creation_flags(self) -> int:
        """Flags to pass to ``Popen(creationflags=...)``."""

    def protect(self, process_id: int) -> None:
        """Guard and then let the just-created process run; raise ``ProcessGuardUnavailable`` if impossible."""

    def release(self) -> None:
        """Drop the guard after the process has exited."""


class NoProcessGuard:
    """No orphan protection (non-Windows platforms)."""

    creation_flags = 0

    def protect(self, process_id: int) -> None:
        """Nothing to do: the process already runs."""

    def release(self) -> None:
        """Nothing to release."""


class WindowsJobGuard:
    """Create suspended → assign to a kill-on-close job → resume (see the module docstring)."""

    creation_flags = CREATE_SUSPENDED | CREATE_NO_WINDOW

    def __init__(self, api: JobApi | None = None) -> None:
        """Use the real Win32 API unless ``api`` is given."""
        self._api = api or Win32JobApi()
        self._job: int | None = None

    @property
    def job(self) -> int | None:
        """Return the job handle while a process is guarded."""
        return self._job

    def protect(self, process_id: int) -> None:
        """Assign and resume ``process_id``; terminate it (it never ran) if either step fails."""
        try:
            job = self._api.create_kill_on_close_job()
        except OSError as error:
            self._api.terminate(process_id)
            raise ProcessGuardUnavailable(f"Could not create a job object: {error}") from error
        try:
            self._api.assign(job, process_id)
        except OSError as error:
            self._api.terminate(process_id)
            self._api.close(job)
            raise ProcessGuardUnavailable(f"Could not assign the server process to a job object: {error}") from error
        self._job = job
        try:
            self._api.resume_primary_thread(process_id)
        except OSError as error:
            self._api.terminate(process_id)
            self.release()
            raise ProcessGuardUnavailable(f"Could not resume the server process: {error}") from error

    def release(self) -> None:
        """Close the job handle; call after the process has exited."""
        job, self._job = self._job, None
        if job is not None:
            self._api.close(job)


def default_process_guard() -> ProcessGuard:
    """Return the guard for this platform."""
    return WindowsJobGuard() if sys.platform == "win32" else NoProcessGuard()


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("r", "w", "o", "rb", "wb", "ob")]


class _BasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _ExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class _ThreadEntry(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ThreadID", wintypes.DWORD),
        ("th32OwnerProcessID", wintypes.DWORD),
        ("tpBasePri", wintypes.LONG),
        ("tpDeltaPri", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
    ]


class Win32JobApi:
    """``JobApi`` implemented with kernel32 through ``ctypes`` (Windows only)."""

    def __init__(self) -> None:
        """Bind the kernel32 functions with explicit signatures."""
        if sys.platform != "win32":  # pragma: no cover - guarded by default_process_guard
            raise OSError("Job objects are only available on Windows.")
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32 = k32
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
        k32.SetInformationJobObject.restype = wintypes.BOOL
        k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.AssignProcessToJobObject.restype = wintypes.BOOL
        k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
        k32.TerminateProcess.restype = wintypes.BOOL
        k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
        k32.CloseHandle.restype = wintypes.BOOL
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
        k32.Thread32First.restype = wintypes.BOOL
        k32.Thread32First.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry))
        k32.Thread32Next.restype = wintypes.BOOL
        k32.Thread32Next.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ThreadEntry))
        k32.OpenThread.restype = wintypes.HANDLE
        k32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.ResumeThread.restype = wintypes.DWORD
        k32.ResumeThread.argtypes = (wintypes.HANDLE,)
        k32.IsProcessInJob.restype = wintypes.BOOL
        k32.IsProcessInJob.argtypes = (wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL))

    def create_kill_on_close_job(self) -> int:
        """Create the job and set ``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` (no memory or CPU limits)."""
        job = self._k32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _ExtendedLimit()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self._k32.SetInformationJobObject(
            job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, ctypes.byref(info), ctypes.sizeof(info)
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self._k32.CloseHandle(job)
            raise error
        return int(job)

    def assign(self, job: int, process_id: int) -> None:
        """Assign the process to ``job``."""
        handle = self._open_process(process_id, _PROCESS_SET_QUOTA | _PROCESS_TERMINATE)
        try:
            if not self._k32.AssignProcessToJobObject(job, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self._k32.CloseHandle(handle)

    def resume_primary_thread(self, process_id: int) -> None:
        """Find the process's threads and resume them (a new suspended process has one)."""
        snapshot = self._k32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
        if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        resumed = 0
        try:
            entry = _ThreadEntry()
            entry.dwSize = ctypes.sizeof(_ThreadEntry)
            more = self._k32.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.th32OwnerProcessID == process_id:
                    thread = self._k32.OpenThread(_THREAD_SUSPEND_RESUME, False, entry.th32ThreadID)
                    if not thread:
                        raise ctypes.WinError(ctypes.get_last_error())
                    try:
                        if self._k32.ResumeThread(thread) == 0xFFFFFFFF:
                            raise ctypes.WinError(ctypes.get_last_error())
                        resumed += 1
                    finally:
                        self._k32.CloseHandle(thread)
                more = self._k32.Thread32Next(snapshot, ctypes.byref(entry))
        finally:
            self._k32.CloseHandle(snapshot)
        if resumed == 0:
            raise OSError(f"No thread of process {process_id} was found to resume.")

    def terminate(self, process_id: int) -> None:
        """Terminate the process, ignoring errors (it may already be gone)."""
        try:
            handle = self._open_process(process_id, _PROCESS_TERMINATE)
        except OSError:
            return
        try:
            self._k32.TerminateProcess(handle, 1)
        finally:
            self._k32.CloseHandle(handle)

    def close(self, job: int) -> None:
        """Close the job handle."""
        self._k32.CloseHandle(job)

    def is_in_job(self, job: int, process_id: int) -> bool:
        """Return whether the process belongs to ``job``."""
        handle = self._open_process(process_id, _PROCESS_QUERY_LIMITED_INFORMATION)
        try:
            result = wintypes.BOOL()
            if not self._k32.IsProcessInJob(handle, job, ctypes.byref(result)):
                raise ctypes.WinError(ctypes.get_last_error())
            return bool(result.value)
        finally:
            self._k32.CloseHandle(handle)

    def _open_process(self, process_id: int, access: int) -> int:
        handle = self._k32.OpenProcess(access, False, process_id)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(handle)
