# ADR 0001: Adopt Clean-lite Architecture

**Status:** Accepted

## Context

MCServer 2.0 needs clear boundaries while it incrementally replaces the legacy application. A full Clean Architecture implementation would add ceremony before the product has enough use cases to justify it.

## Decision

We adopt Clean-lite Architecture with manual dependency injection. Domain contains framework-independent business rules. Application contains use cases and dependency abstractions. Infrastructure provides adapters for filesystem, processes, and external services. Presentation contains PySide6 views and lightweight view models that call application use cases.

Dependencies point inward: Presentation and Infrastructure depend on Application; Application depends on Domain; Domain depends on no other project layer. Bootstrap composes concrete dependencies at the application edge.

## Consequences

New modules begin as a domain concept or application use case, then receive infrastructure and presentation adapters only where needed. This preserves testability and supports gradual legacy replacement without premature complexity.
