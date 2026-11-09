"""Tests for Java runtime discovery without depending on a system Java installation."""

from pathlib import Path

import pytest

from mcserver.infrastructure.java_runtime import JavaRuntimeNotFound, JavaRuntimeResolver, JavaRuntimeSource


def test_prefers_a_valid_bundled_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundled_java = tmp_path / "java.exe"
    bundled_java.touch()
    monkeypatch.setattr(JavaRuntimeResolver, "_is_usable", staticmethod(lambda _path: True))

    runtime = JavaRuntimeResolver((bundled_java,)).resolve()

    assert runtime.executable == bundled_java.resolve()
    assert runtime.source is JavaRuntimeSource.BUNDLED


def test_raises_when_no_candidate_or_system_java_is_usable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("mcserver.infrastructure.java_runtime.shutil.which", lambda _name: None)

    with pytest.raises(JavaRuntimeNotFound):
        JavaRuntimeResolver((tmp_path / "missing-java",)).resolve()
