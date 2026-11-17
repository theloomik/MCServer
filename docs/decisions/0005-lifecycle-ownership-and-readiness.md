# ADR 0005: The Coordinator Owns the Lifecycle; Readiness Comes From the Console

**Status:** Accepted

## Context

Before M1, both `ServerCoordinator` and `SubprocessServerRunner` kept a `ServerState`, and both switched to RUNNING as soon as `Popen` returned. Minecraft then still needs seconds to minutes to load the world, so the GUI said "Running" while players could not join, and nothing noticed a server that never finished starting.

## Decision

- **One owner.** `ServerCoordinator` (Application) is the only owner of `ServerState`. The `ServerRunner` port reports events only: console lines (`on_output`), the exit code (`on_exit`, once, after all output) and the `process_id`. It has no state field.
- **Readiness is a domain rule.** `domain/readiness.py` decides from one console line whether the server is ready. The default rule matches the line every common server type prints once it accepts players: `Done (<seconds>s)! For help, type "help"` (Vanilla, Paper, Purpur, Spigot, Fabric, Forge; ANSI colours ignored). New server types add a rule; nothing else changes. Echoed user commands (`OutputStream.COMMAND`) never count.
- **States.** `start_server` moves STOPPED → STARTING and returns a `StartReport` (with non-blocking `LaunchWarning`s). The first ready line moves STARTING → RUNNING.
- **Startup timeout without a kill.** If no ready line arrives within the startup timeout (default 600 s), the coordinator records a `START_TIMEOUT` failure and starts a **graceful** stop (STARTING → STOPPING, a transition added for this and for Stop pressed during startup). If that stop also times out, the server stays STOPPING and the user may Kill it (ADR 0006). The timer is a `Scheduler` port, so tests fire it without waiting.
- **Failures carry evidence.** An exit that nobody requested is recorded as `UNEXPECTED_EXIT` with the exit code, the last 40 console lines and a `FailureHint` from `domain/diagnostics.py` (EULA, port in use, Java too old, out of memory, corrupt JAR). `CoordinatorStatus.last_failure` exposes it to the GUI.
- **Preflight errors stay typed.** The runner factory checks launch preconditions before anything runs and raises `EulaNotAccepted`, `JavaNotFound`, `JavaVersionTooOld` or `ServerWorldInUse` unchanged, so the GUI can ask for consent or show Java guidance. Any other factory or spawn error becomes `ServerStartFailed`.
- **Every API takes `server_id`** (`send_command(server_id, text)`), so a future multi-server coordinator (ADR 0002) is an internal change.

## Consequences

The GUI's "Running" now means "players can join". A server type that prints a different ready line stays STARTING until the timeout and is then stopped gracefully; such a type needs a readiness rule. The coordinator is the single place to reason about lifecycle races; events from an older process are ignored through a generation counter. Fake runners in tests must emit a ready line (`tests/runtime_fakes.py`).
