# ADR 0006: Graceful Shutdown, Explicit Kill and the Windows Job Object

**Status:** Accepted

## Context

Before M1, a stop sent `stop`, waited 10 seconds and then called `terminate()`, which on Windows is `TerminateProcess`: a hard kill that can lose or damage world data while the server is still saving. When MCServer itself crashed, `java.exe` kept running as an orphan that held the port and `session.lock` and could only be ended from Task Manager.

## Decision

### Stop is always graceful

- `ServerRunner.stop(timeout)` sends `stop`, waits and returns whether the process exited. It never forces termination. `wait_for_exit(timeout)` waits again without sending anything.
- `ServerCoordinator.stop_server(timeout=None)` uses a configurable timeout (default **90 s**). If the process is still running afterwards it raises `ServerStopTimedOut`; the server stays **STOPPING** and `CoordinatorStatus.stop_timed_out` is set. Pressing Stop again only waits again.
- Normal operation never kills automatically.

### Forced termination happens in exactly two cases

1. **Explicit Kill.** `kill_server()` (state KILLING) runs only after the user confirmed a warning that changes since the last autosave can be lost. The GUI offers Kill only while a server is STOPPING.
2. **MCServer itself ended.** Windows closes the Job Object (below) and terminates Java.

### What happens when

| Situation | Behaviour | World data |
| --- | --- | --- |
| Stop button | `stop`, wait up to 90 s; on timeout STOPPING + Kill offered | Full save |
| Startup timeout (ADR 0005) | Failure reported, then the same graceful stop | Full save |
| Closing the window with a server running | Confirm → graceful stop → close once stopped. On timeout: Keep waiting, Kill, or Cancel the close | Full save unless the user chooses Kill |
| Windows sign-out / shutdown | `commitDataRequest` runs the graceful stop on the GUI thread and registers `ShutdownBlockReasonCreate`. Windows may still force-close after its own limit | Usually full save, not guaranteed |
| Unhandled Python exception | `sys.excepthook` logs, makes **one** graceful-stop attempt limited to **30 s**, then exits the event loop. If Java is still running, MCServer exits anyway: the Job Object terminates Java and the session marker stays | Full save if Java stops within 30 s; otherwise as a hard crash |
| Hard crash, End task, `taskkill /F` | No MCServer code runs; Windows closes the job handle and terminates Java at once | Changes since the last autosave (about 5 min by default) can be lost; a chunk being written can be damaged |
| Next launch after any of the last three | A leftover `<server>/.mcserver/running` marker produces one notice per incident naming the server and the possible data loss. No recovery action exists before backups (M3) | Information only |

### Process creation and job assignment

Java must never run unguarded (`infrastructure/windows_job.py`):

1. `Popen(..., creationflags=CREATE_SUSPENDED)`: the process exists but has run no code.
2. `AssignProcessToJobObject` with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Only the server's process tree joins the job, never MCServer.
3. Resume the primary thread (found with `CreateToolhelp32Snapshot`, because `subprocess` closes the thread handle).
4. If step 2 or 3 fails, the never-run process is terminated and the start fails with `ProcessGuardUnavailable`.

The remaining gap is MCServer dying between steps 1 and 2; the child then stays suspended, has run no code and holds no port or world lock. No memory limit is set on the job: a JVM above `-Xmx` (metaspace, native memory) would otherwise be killed mid-save. After the server process exits, the job handle is closed before the output readers are joined, so children left behind cannot keep the pipes open.

### Why kill-on-close despite the data risk

An orphan keeps the port and `session.lock`, uses RAM, is invisible in MCServer and can only be ended from Task Manager, which also kills it without saving. MCServer cannot re-attach to an orphan because its stdin is gone. A graceful stop of orphans through RCON is a candidate for 2.1.

## Consequences

MCServer never promises absolute world safety: normal shutdown is graceful and designed to preserve world data, while hard crashes, power loss and forced termination can still lose or damage data. Backups (M3) are the recovery path. Windows-specific behaviour is covered by tests marked by platform (`tests/integration/infrastructure/test_job_object_processes.py`); on other platforms no guard is used.
