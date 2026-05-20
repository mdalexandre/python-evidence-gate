# ADR 0001: Initial stack choice

**Status**: Accepted, scaffolded by /spr-build.
**Decision**: language `python-3.12`, package manager `uv`, frameworks: .

## Rationale (per SPR Chapter 4.1 and 5.1)

Stack selected to match the manifest's declared targets and operator preferences.
See SPR Chapter 4.1 for architectural-style rationale and Chapter 5.1 for methodology.

## Consequences

Every dependency is pinned in the package manifest; the stack is reproducible.
