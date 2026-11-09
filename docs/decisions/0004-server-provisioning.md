# ADR 0004: Server Provisioning Creates Only New Files and Rolls Back Only Its Own

**Status:** Accepted

## Context

`ServerManagement` stores configuration records, but a new server also needs its directory and server JAR on disk. Preparing files touches user data, so a failure halfway through (directory created, JAR copy failed) must neither leave an unexplained half-provisioned server nor risk deleting anything the user already had.

## Decision

- `ServerProvisioning.provision_server(server_id, source_jar)` (Application) reads the stored `ServerConfiguration`, then: checks the source JAR, creates `directory`, copies the JAR as `jar_file`. It never writes configurations. `source_jar` is passed as a string so Application stays free of filesystem types.
- One port, `ServerProvisioningFilesystem`, covers the four file operations (check source, create directory, install JAR, remove created directory). Rollback needs all four together, so separate ports would only scatter one concern.
- `LocalServerFilesystem` (Infrastructure) is the only code that touches the disk:
  - names must be safe single path segments (the domain rule), and targets must resolve directly inside the servers root; server directories that are symbolic links are refused;
  - creation is exclusive (`mkdir` without `exist_ok`, `open(..., "xb")`), so existing directories and JARs are conflicts, never overwritten, even under a concurrent writer;
  - the source JAR is only read.
- The target directory must not exist. Therefore everything rollback removes was created by the same call: a partial JAR (`unlink`) and the new directory (`rmdir`, which refuses non-empty directories).
- If rollback cannot finish, `ProvisioningRollbackFailed` carries the original error and `leftovers` (paths relative to the root) for manual cleanup. Nothing is retried or force-deleted.

### One-step server creation

Creating a record and provisioning it separately leaves a window where a record points to a directory that was never prepared. `ServerCreation.create_server(...)` (Application, `ServerRuntime.server_creation`) orchestrates the two existing use cases as a compensating workflow, not a transaction:

1. `ServerManagement.create_server` stores the record. Its errors (invalid values, duplicate `server_id`, directory used by another server, storage failure) are raised unchanged and no files are touched.
2. `ServerProvisioning.provision_server` prepares the files and cleans up its own files on failure, as described above.
3. If provisioning fails, the record from step 1 is removed, but only if it is still identical to what step 1 stored, and the original provisioning error is raised. The workflow itself never deletes files.

If the record cannot be removed, or was changed by someone else and is kept, `ServerCreationRollbackFailed` exposes both `provisioning_error` (with its `leftovers`) and `rollback_error`. The record is visible to other readers between steps 1 and 3, and a crash in that window can leave it behind.

## Consequences

Provisioning is safe to call from the GUI without Java (`build_server_provisioning`, `ServerRuntime.provisioning`). Provisioning into an existing folder (for example adding a JAR to an imported server) is not supported yet and would need its own rules. Provisioning does not download JARs, check that a JAR is a Minecraft server, accept the EULA, write `server.properties`, launch servers or delete server files. A process killed mid-copy can leave a partial JAR, which the next attempt reports as a directory conflict rather than overwriting.
