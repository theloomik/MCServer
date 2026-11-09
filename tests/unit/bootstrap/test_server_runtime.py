"""Tests for composing the server runtime without launching Java."""

from pathlib import Path

from mcserver.application.server_coordinator import ServerCoordinator
from mcserver.application.server_output import ServerOutputBuffer
from mcserver.bootstrap.server_runtime import build_server_coordinator, build_server_runtime
from mcserver.infrastructure.java_runtime import JavaRuntime, JavaRuntimeResolver, JavaRuntimeSource


class StubJavaResolver(JavaRuntimeResolver):
    """Return a fixed Java path without probing the system."""

    def resolve(self) -> JavaRuntime:
        return JavaRuntime(Path("java"), JavaRuntimeSource.SYSTEM)


def test_runtime_shares_one_output_buffer_with_runner_factory(tmp_path: Path) -> None:
    runtime = build_server_runtime(tmp_path, StubJavaResolver(), output_capacity=50)

    assert isinstance(runtime.coordinator, ServerCoordinator)
    assert isinstance(runtime.output, ServerOutputBuffer)
    assert runtime.output.capacity == 50
    assert runtime.coordinator._runner_factory._output_sink is runtime.output  # type: ignore[attr-defined]


def test_build_server_coordinator_remains_available(tmp_path: Path) -> None:
    assert isinstance(build_server_coordinator(tmp_path, StubJavaResolver()), ServerCoordinator)
