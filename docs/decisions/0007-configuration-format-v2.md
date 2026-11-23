# ADR 0007: Server Configuration Format Version 2

**Status:** Accepted

## Context

ADR 0003 stored only `server_id`, `directory`, `jar_file` and `memory_mb`. M2 needs a name users can change, extra Java options, a Java executable per server and optional labels, while `server_id` must stay stable (it names the server in the coordinator, markers and messages).

## Decision

- `server_configurations.json` moves to `"format_version": 2`. Each server keeps the four required fields and gains five optional ones:

  | Field | Meaning | Rule |
  | --- | --- | --- |
  | `display_name` | Name shown in the GUI; empty means "use `server_id`" | ≤ 64 printable characters, no leading/trailing spaces |
  | `jvm_arguments` | Extra Java options, passed as separate items (never through a shell) | ≤ 32 items; `-Xmx`, `-Xms`, `-XX:MaxRAM*`, `-jar`, `-cp`, `-classpath`, `--class-path` are reserved because MCServer sets them |
  | `java_path` | Java executable for this server, overriding detection | non-empty path; checked with `JavaRuntimeProvider.inspect` at start |
  | `server_type`, `minecraft_version` | Optional labels | ≤ 32 printable characters |

- **Reading:** version 1 and version 2 are both read; a version-1 entry with version-2 fields is corrupt. Any other version is refused and never overwritten (ADR 0003 unchanged).
- **Writing:** always version 2, so a version-1 file is upgraded on its first write. Nothing is migrated eagerly.
- **Renaming** changes `display_name`; `server_id` never changes. `update_server` refuses to change `directory` or `jar_file` while that server is active (`ServerIsRunning`); every other change applies on the next start.
- Launch order: `java -Xms<m>M -Xmx<m>M <jvm_arguments…> -jar <jar> nogui`.

## Consequences

An MCServer 2.0 alpha that only knows version 1 cannot read a file written by this version. That is acceptable before 2.0.0 because no release depends on version 1. Future fields follow the same pattern: optional with a safe default, plus a version bump only when old readers must be stopped.
