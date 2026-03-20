# ADR-033: ReBAC Authorization Evolution Strategy

**Status:** Accepted  
**Date:** 2026-03-19  
**Deciders:** Founder  

---

## Context

The current `authz-service` enforces RBAC v1: flat roles and scope strings. This model cannot represent household relationship hierarchies, device-trust conditions, or approval-track escalation in a composable way.

As Computer moves toward local-first family surfaces, policy tuning, and memory export, we need an authorization model that can answer: "Can user X access resource Y given their relationship to household Z and their current auth track?"

## Decision

Migrate authorization to **Relationship-Based Access Control (ReBAC)** using **OpenFGA** (Zanzibar-style authorization) as the target.

The migration proceeds in three phases:
1. RBAC v1 + scopes (current)
2. Hybrid: new paths go through OpenFGA; existing roles stay in authz-service (V4)
3. Full ReBAC: all authorization migrated to OpenFGA; RBAC v1 retired (V5)

The authorization model introduces an **explicit two-track auth split**:
- **Session track**: standard OAuth 2.1 token; suitable for identity, browsing, normal queries
- **Approval track**: passkey re-auth (WebAuthn); required for sensitive approvals, memory export, policy changes, identity recovery

## Consequences

**Positive:**
- Authorization can model household relationships, not just roles
- Approval track is a first-class concept enforced at the auth layer
- OpenFGA queries are auditable and testable
- Zanzibar-style tuples enable fine-grained memory sharing

**Negative:**
- Migration complexity: two auth systems in parallel during Phase 2
- OpenFGA requires a running store (Postgres-backed); adds infrastructure dependency
- Tuple consistency must be maintained across user/device lifecycle events

## Alternatives Considered

- **RBAC v2 with conditions**: Would require a custom rule engine; still cannot model relationship graphs natively
- **ABAC**: Attribute-based access control is powerful but lacks the graph query semantics needed for household hierarchies

## Schema Location

`packages/authz-model/openfga_schema.fga`

See also: `docs/architecture/rebac-auth-evolution.md`
