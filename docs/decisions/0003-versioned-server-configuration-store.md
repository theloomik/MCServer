# ADR 0003: Versioned JSON Store for Server Configurations

**Status:** Accepted

## Context

MCServer 2.0 launched servers from the legacy `servers_config.json` through a read-only adapter. That format has no version, stores absolute paths that break when the servers folder moves, and is owned by legacy code. Upcoming features (listing, creating, editing, deleting servers) need storage that the new architecture owns.

## Decision

Server configurations are stored in `<servers root>/server_configurations.json`:

```json
{
  "format_version": 1,
  "servers": [
    {"server_id": "survival", "directory": "survival", "jar_file": "paper.jar", "memory_mb": 4096}
  ]
}
```

- `ServerConfiguration` (Domain) holds only what cannot be derived: identifier, server folder name relative to the root, JAR file name inside that folder, and memory. Absolute paths, JVM arguments, `nogui`, the Java executable and lifecycle state are derived or runtime-only and never stored.
- `ServerConfigurationRepository` (Application port) offers `list_all`, `get`, `add`, `update` and `remove`. `add` and `update` are separate so creating a server can never silently overwrite another; directories must be unique (case-insensitively).
- `JsonServerConfigurationRepository` (Infrastructure) validates the whole file strictly. A corrupt file or an unknown `format_version` makes every operation fail and nothing is written, so damaged or newer data is never overwritten. Writes use a temporary file, `fsync` and atomic `os.replace`.
- Legacy data is imported only on explicit request through `LegacyServerConfigurationImporter`, which never modifies `servers_config.json` and skips servers already present, so it can be repeated safely.
- Bootstrap exposes the store as `ServerRuntime.configurations`. Launching still reads the legacy file by default; `launch_from_configuration_store=True` switches launching to the new store.

## Consequences

Moving the servers root no longer invalidates configurations. A future format change bumps `format_version` and adds an explicit upgrade step. Concurrent writes from several processes are not coordinated; MCServer runs as a single desktop process. Until the legacy UI writes through the new store, both files may coexist, and the legacy file remains the launch source unless the new one is explicitly enabled.
