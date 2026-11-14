"""Unit tests for the Job Object guard sequence with a fake Win32 API (M1-BE-06)."""

from __future__ import annotations

import pytest

from mcserver.application.errors import ProcessGuardUnavailable
from mcserver.infrastructure.windows_job import CREATE_SUSPENDED, NoProcessGuard, WindowsJobGuard


class FakeJobApi:
    def __init__(self, *, fail_create: bool = False, fail_assign: bool = False, fail_resume: bool = False) -> None:
        self.fail_create = fail_create
        self.fail_assign = fail_assign
        self.fail_resume = fail_resume
        self.calls: list[str] = []

    def create_kill_on_close_job(self) -> int:
        self.calls.append("create")
        if self.fail_create:
            raise OSError("no jobs")
        return 77

    def assign(self, job: int, process_id: int) -> None:
        self.calls.append(f"assign:{job}:{process_id}")
        if self.fail_assign:
            raise OSError("access denied")

    def resume_primary_thread(self, process_id: int) -> None:
        self.calls.append(f"resume:{process_id}")
        if self.fail_resume:
            raise OSError("no thread")

    def terminate(self, process_id: int) -> None:
        self.calls.append(f"terminate:{process_id}")

    def close(self, job: int) -> None:
        self.calls.append(f"close:{job}")

    def is_in_job(self, job: int, process_id: int) -> bool:
        return True


def test_process_is_created_suspended_assigned_then_resumed() -> None:
    api = FakeJobApi()
    guard = WindowsJobGuard(api)

    guard.protect(10)

    assert guard.creation_flags == CREATE_SUSPENDED
    assert api.calls == ["create", "assign:77:10", "resume:10"]
    assert guard.job == 77
    guard.release()
    assert api.calls[-1] == "close:77" and guard.job is None


@pytest.mark.parametrize(
    ("api", "expected"),
    [
        (FakeJobApi(fail_create=True), ["create", "terminate:10"]),
        (FakeJobApi(fail_assign=True), ["create", "assign:77:10", "terminate:10", "close:77"]),
        (FakeJobApi(fail_resume=True), ["create", "assign:77:10", "resume:10", "terminate:10", "close:77"]),
    ],
)
def test_a_failed_step_terminates_the_never_run_process(api: FakeJobApi, expected: list[str]) -> None:
    guard = WindowsJobGuard(api)

    with pytest.raises(ProcessGuardUnavailable):
        guard.protect(10)

    assert api.calls == expected
    assert "resume:10" not in api.calls or api.fail_resume  # never resumed unless resuming itself failed
    assert guard.job is None


def test_release_without_a_job_is_safe() -> None:
    api = FakeJobApi()
    WindowsJobGuard(api).release()
    assert api.calls == []


def test_no_guard_does_nothing() -> None:
    guard = NoProcessGuard()
    guard.protect(10)
    guard.release()
    assert guard.creation_flags == 0
