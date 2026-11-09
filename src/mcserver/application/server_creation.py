"""Use case that creates a server's configuration and files in one step."""

from mcserver.application.errors import (
    ServerConfigurationNotFound,
    ServerConfigurationStorageError,
    ServerCreationRollbackFailed,
    ServerProvisioningError,
)
from mcserver.application.server_management import ServerManagement
from mcserver.application.server_provisioning import ProvisionedServer, ServerProvisioning
from mcserver.domain.server_configuration import ServerConfiguration


class ServerCreation:
    """Create a configuration record and provision its files, or leave neither behind.

    This is a compensating workflow, not a transaction:

    1. ``ServerManagement.create_server`` validates and stores the record. If
       it fails (invalid values, duplicate ``server_id``, directory used by
       another server, storage error), nothing was changed and that error is
       raised unchanged; no files are touched.
    2. ``ServerProvisioning.provision_server`` creates the directory and copies
       the JAR, cleaning up its own files on failure (see ``ServerProvisioning``).
    3. If provisioning fails, the record from step 1 is removed and the
       original provisioning error is raised. The record is only removed if it
       is still exactly the one created here; files are never deleted by this
       workflow.

    If the record cannot be removed (or was changed meanwhile and is kept),
    ``ServerCreationRollbackFailed`` carries both the provisioning error and
    the rollback error. Leftover files reported by provisioning stay available
    through ``provisioning_error.leftovers``. Between steps 1 and 3 the record
    is briefly visible to other readers of the same repository, and a process
    crash in that window can leave it behind.
    """

    def __init__(self, management: ServerManagement, provisioning: ServerProvisioning) -> None:
        """Coordinate existing configuration management and provisioning."""
        self._management = management
        self._provisioning = provisioning

    def create_server(
        self, *, server_id: str, directory: str, jar_file: str, memory_mb: int, source_jar: str
    ) -> ProvisionedServer:
        """Store the configuration, provision its directory and JAR, and return the result."""
        configuration = self._management.create_server(
            server_id=server_id, directory=directory, jar_file=jar_file, memory_mb=memory_mb
        )
        try:
            return self._provisioning.provision_server(configuration.server_id, source_jar)
        except (ServerProvisioningError, ServerConfigurationStorageError) as error:
            self._roll_back_configuration(configuration, error)
            raise

    def _roll_back_configuration(self, created: ServerConfiguration, provisioning_error: Exception) -> None:
        """Remove the record created by this call, but only if it is still unchanged."""
        try:
            current = self._management.get_server(created.server_id)
            if current != created:
                raise ServerCreationRollbackFailed(created.server_id, provisioning_error, None) from provisioning_error
            self._management.delete_server(created.server_id)
        except ServerConfigurationNotFound:
            return  # already gone; nothing left to undo
        except ServerConfigurationStorageError as rollback_error:
            raise ServerCreationRollbackFailed(
                created.server_id, provisioning_error, rollback_error
            ) from rollback_error
