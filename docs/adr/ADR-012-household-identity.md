# ADR-012: Household identity, roles, and permissions model

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

The Personal Intelligence Plane serves multiple household members with different access levels. Without a formal identity and role model, any household member could access any data or trigger any action.

## Decision

Introduce `services/identity-service/` as the authoritative source of household identity, roles, and permissions.

### Role model

Four roles (see full definition in household-roles-and-permissions.md):
- `FOUNDER_ADMIN` — Full access to all planes
- `ADULT_MEMBER` — Full household access; limited site access
- `CHILD_GUEST` — Conversational assistant only; no sensitive data
- `MAINTENANCE_OPERATOR` — Ops access; no household data

### Identity service responsibilities

- Authenticate household members (session tokens)
- Resolve session → user_id → role
- Manage household member accounts
- Support time-bounded access (temporary guests, maintenance visits)

### Integration point

context-router calls identity-service to resolve session → user identity before producing the context envelope. All downstream services receive user_id + role in the context envelope; they do not call identity-service directly.

## Consequences

- Identity is a service, not an embedded concern.
- Role changes take effect immediately (session tokens are short-lived; next request picks up new role).
- Guest accounts can be created and revoked by FOUNDER_ADMIN without engineering effort.
- identity-service has no dependencies on orchestrator or control services; it is isolated.
