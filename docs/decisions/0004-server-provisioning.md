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

## Consequences

Provisioning is safe to call from the GUI without Java (`build_server_provisioning`, `ServerRuntime.provisioning`). Provisioning into an existing folder (for example adding a JAR to an imported server) is not supported yet and would need its own rules. Provisioning does not download JARs, check that a JAR is a Minecraft server, accept the EULA, write `server.properties`, launch servers or delete server files. A process killed mid-copy can leave a partial JAR, which the next attempt reports as a directory conflict rather than overwriting.
