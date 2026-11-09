"""Use case for preparing the files of a configured server."""

from dataclasses import dataclass

from mcserver.application.errors import ProvisioningRollbackFailed, ServerProvisioningError
from mcserver.application.ports import ServerConfigurationRepository, ServerProvisioningFilesystem
from mcserver.domain.server_configuration import ServerConfiguration


@dataclass(frozen=True, slots=True)
class ProvisionedServer:
    """A server whose directory was created and whose JAR was installed."""

    configuration: ServerConfiguration
    source_jar: str
    """The user-selected JAR that was copied; it is never modified."""


class ServerProvisioning:
    """Create the directory of a configured server and copy its JAR into it.

    Provisioning only prepares files. It reads the stored configuration and
    never changes it, and it does not launch servers, accept the EULA or write
    ``server.properties``.

    The target directory must not exist yet, so everything removed during a
    rollback was created by the same call. Failure handling:

    * invalid source JAR: nothing is created;
    * directory already exists or cannot be created: nothing is created;
    * JAR copy fails: the partial JAR and the new directory are removed and the
      original error is raised;
    * the rollback itself fails: ``ProvisioningRollbackFailed`` is raised with
      the original error and the paths left on disk, for manual cleanup.
    """

    def __init__(self, repository: ServerConfigurationRepository, filesystem: ServerProvisioningFilesystem) -> None:
        """Read configurations from ``repository`` and prepare files through ``filesystem``."""
        self._repository = repository
        self._filesystem = filesystem

    def provision_server(self, server_id: str, source_jar: str) -> ProvisionedServer:
        """Provision ``server_id`` from the JAR at ``source_jar`` and describe the result.

        Raises ``ServerConfigurationNotFound`` for an unknown server, a
        ``ServerProvisioningError`` subclass for file problems, and
        ``ServerConfigurationStorageError`` if the configuration cannot be read.
        """
        configuration = self._repository.get(server_id)
        self._filesystem.check_source_jar(source_jar)
        self._filesystem.create_directory(configuration.directory)
        try:
            self._filesystem.install_jar(configuration.directory, configuration.jar_file, source_jar)
        except ServerProvisioningError as error:
            self._roll_back_directory(server_id, configuration.directory, error)
            raise
        return ProvisionedServer(configuration=configuration, source_jar=source_jar)

    def _roll_back_directory(self, server_id: str, directory: str, original: ServerProvisioningError) -> None:
        """Remove the directory this call created, or report why it cannot be removed."""
        if original.leftovers:
            # The partial JAR is still inside, so the directory cannot be removed safely.
            raise ProvisioningRollbackFailed(server_id, original, (*original.leftovers, directory)) from original
        try:
            self._filesystem.remove_created_directory(directory)
        except ServerProvisioningError as rollback_error:
            raise ProvisioningRollbackFailed(server_id, original, (directory,)) from rollback_error
