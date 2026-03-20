# ADR-013: Personal memory is partitioned by person, household, and shared context

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

A household assistant with undifferentiated memory would blur private information with shared information. Household member A's private reminders and notes should not be accessible to household member B, even if they share the same household.

## Decision

Memory is partitioned into three non-overlapping scopes (see personal-memory-spec.md):
- `PERSONAL` — individual-only; not accessible to others regardless of role
- `HOUSEHOLD_SHARED` — all non-CHILD household members; shared coordination data
- `SITE_SYSTEM` — site operations data; FOUNDER_ADMIN and MAINTENANCE_OPERATOR only

### Enforcement mechanism

1. Every memory read/write call includes an explicit `scope` parameter.
2. memory-service validates the requesting user has access to the requested scope.
3. context-router includes `eligible_memory_scopes` in the context envelope.
4. model-router passes only eligible scopes to memory-service calls.
5. Scope violations return `ScopeViolationError`, never a partial result.

### No automatic scope promotion

Information written to PERSONAL scope never automatically appears in HOUSEHOLD_SHARED. A user must explicitly share information to move it to a broader scope.

## Consequences

- Voice assistant in FAMILY mode cannot reveal one person's private reminders to the room.
- FOUNDER_ADMIN cannot read another adult's PERSONAL memory through the assistant (even with admin role).
- Memory exports are scoped: PERSONAL export includes only that person's data.
- Implementation complexity: memory-service must enforce scope at the query level, not just at the application level.
