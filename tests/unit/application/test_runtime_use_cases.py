"""EULA consent in provisioning, unclean-shutdown health and Java setup use cases."""

from __future__ import annotations

import pytest

from mcserver.application.errors import (
    InvalidJavaExecutable,
    JavaNotFound,
    ProvisioningRollbackFailed,
    ServerFilesystemError,
)
from mcserver.application.java_setup import JavaSetup
from mcserver.application.ports import JavaInstallation
from mcserver.application.server_health import ServerHealth
from mcserver.application.server_provisioning import ServerProvisioning
from mcserver.domain.server_configuration import ServerConfiguration
from tests.runtime_fakes import MemoryMarkers


class Repository:
    def __init__(self) -> None:
        self.configuration = ServerConfiguration("survival", "survival", "paper.jar", 2048)

    def get(self, server_id: str) -> ServerConfiguration:
        return self.configuration


class Files:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.install_error: ServerFilesystemError | None = None
        self.remove_eula_error: ServerFilesystemError | None = None
        self.eula = False

    def check_source_jar(self, source_jar: str) -> None:
        self.calls.append("check")

    def create_directory(self, directory: str) -> None:
        self.calls.append("create")

    def accept_eula(self, directory: str) -> None:
        self.calls.append("eula")
        self.eula = True

    def eula_accepted(self, directory: str) -> bool:
        return self.eula

    def install_jar(self, directory: str, jar_file: str, source_jar: str) -> None:
        self.calls.append("install")
        if self.install_error is not None:
            raise self.install_error

    def remove_eula(self, directory: str) -> None:
        self.calls.append("remove-eula")
        if self.remove_eula_error is not None:
            raise self.remove_eula_error
        self.eula = False

    def remove_created_directory(self, directory: str) -> None:
        self.calls.append("remove-dir")


def provisioning(files: Files) -> ServerProvisioning:
    return ServerProvisioning(Repository(), files)  # type: ignore[arg-type]


def test_eula_is_written_only_with_consent() -> None:
    files = Files()
    provisioning(files).provision_server("survival", "paper.jar")
    assert files.calls == ["check", "create", "install"]

    files = Files()
    provisioning(files).provision_server("survival", "paper.jar", accept_eula=True)
    assert files.calls == ["check", "create", "eula", "install"]


def test_failed_jar_copy_removes_the_written_eula_and_the_directory() -> None:
    files = Files()
    files.install_error = ServerFilesystemError("disk full")

    with pytest.raises(ServerFilesystemError):
        provisioning(files).provision_server("survival", "paper.jar", accept_eula=True)

    assert files.calls[-2:] == ["remove-eula", "remove-dir"]
    assert not files.eula


def test_eula_that_cannot_be_removed_is_reported_as_leftover() -> None:
    files = Files()
    files.install_error = ServerFilesystemError("disk full")
    files.remove_eula_error = ServerFilesystemError("locked")

    with pytest.raises(ProvisioningRollbackFailed) as error:
        provisioning(files).provision_server("survival", "paper.jar", accept_eula=True)

    assert error.value.leftovers == ("survival/eula.txt", "survival")
    assert "remove-dir" not in files.calls


def test_eula_can_be_accepted_later_for_an_existing_server() -> None:
    files = Files()
    use_case = provisioning(files)

    assert not use_case.eula_accepted("survival")
    use_case.accept_eula("survival")
    assert use_case.eula_accepted("survival")


def test_unclean_shutdowns_are_reported_until_acknowledged() -> None:
    markers = MemoryMarkers("survival")
    health = ServerHealth(markers)

    [incident] = health.unclean_shutdowns()
    assert incident.server_id == "survival" and incident.started_at

    health.acknowledge("survival")
    assert health.unclean_shutdowns() == ()


def test_unreadable_marker_storage_reports_nothing() -> None:
    class Broken(MemoryMarkers):
        def leftovers(self):  # type: ignore[no-untyped-def]
            raise OSError("disk unavailable")

    assert ServerHealth(Broken()).unclean_shutdowns() == ()


class Provider:
    def __init__(self) -> None:
        self.installed: JavaInstallation | None = None
        self.configured_executable: str | None = None

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        if self.configured_executable == "java8.exe":
            return JavaInstallation("java8.exe", 8, "configured")
        if self.installed is None:
            raise JavaNotFound(minimum_major)
        return self.installed

    def configure(self, executable: str | None) -> JavaInstallation | None:
        if executable not in (None, "java8.exe"):
            raise InvalidJavaExecutable(str(executable))
        self.configured_executable = executable
        return None


def test_java_status_is_detected_on_every_call() -> None:
    provider = Provider()
    setup = JavaSetup(provider)
    assert not setup.status().available

    provider.installed = JavaInstallation("C:/jdk-21/bin/java.exe", 21, "installed")

    assert setup.status().installation == provider.installed


def test_choosing_an_executable_is_validated_and_reported() -> None:
    setup = JavaSetup(Provider())

    status = setup.choose_executable("java8.exe")
    assert status.configured_executable == "java8.exe"
    assert status.installation is not None and status.installation.major_version == 8
    with pytest.raises(InvalidJavaExecutable):
        setup.choose_executable("notepad.exe")
