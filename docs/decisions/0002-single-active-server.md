# ADR 0002: Support One Active Server Initially

**Status:** Accepted

## Context

The first lifecycle and process-management workflows need an unambiguous owner of start, stop, monitoring, and forced termination. Supporting concurrent active servers immediately would multiply coordination and UI complexity.

## Decision

MCServer 2.0 initially permits one active Minecraft server at a time. Lifecycle management therefore represents the selected active server and application use cases will enforce the single-active-server policy.

## Consequences

The domain lifecycle remains an instance model rather than a global singleton, so it can be attached to a server identity later. Future multi-server support can introduce a collection-level coordinator without changing lifecycle transition rules.
