# ADR 0009: Launch Only From the Configuration Store; Import 0.9.1 Servers Explicitly

**Status:** Accepted

## Context

Until M2, `build_server_runtime` launched servers from the legacy `servers_config.json` unless `launch_from_configuration_store=True` was passed. Two launch sources meant two sets of rules and a permanent source of "why does my server not start".

## Decision

- **One launch source.** `build_server_runtime` always launches from `server_configurations.json` (`StoredServerLaunchSettings`). The `launch_from_configuration_store` parameter and the legacy launch path are removed.
- **Import stays explicit and read-only.** `LegacyServerConfigurationRepository` remains only as the read-only source for `ServerManagement.import_legacy_servers` (ADR 0003): it never writes `servers_config.json`, skips servers already present and rejects invalid entries one by one.
- **Paths as 0.9.1 used them.** The importer resolves a server exactly like 0.9.1 launched it: `<directory>/<core_name>`. `jar_path` (where the JAR was copied from) only supplies a file name when `core_name` is missing. A relative `directory` (0.9.1 development runs stored `minecraft_servers\<name>`, relative to the old working directory) is taken by its last part inside the servers root, so the result never depends on the current directory. This was found by a dry run against real 0.9.1 data, which rejected servers whose relative `jar_path` was joined to the folder twice.
- **The GUI offers the import once.** On the first start that finds 0.9.1 servers not yet imported, MCServer asks once (`legacy_import_offered` in the application settings records that it asked, whatever the answer). The import is always available under *File › Import from MCServer 0.9.1…* and in Settings, and repeating it is safe.

## Consequences

A 0.9.1 server cannot be started until it is imported; the start fails with a clear error and the startup offer covers the normal upgrade path. Legacy data is never modified, so 0.9.1 keeps working side by side until it is uninstalled.
