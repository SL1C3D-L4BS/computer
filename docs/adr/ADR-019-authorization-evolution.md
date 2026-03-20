# ADR-019: Authorization Evolution — RBAC v1 to ReBAC v2

**Status:** Accepted (v1 active; v2 planned)  
**Date:** 2026-03-19

## Context
RBAC v1 handles simple role checks but cannot express household-specific relationships ("Alice shares greenhouse access with Bob this week"). V2 needs relationship-based access control.

## Decision
- v1: RBAC policy function in `authz-service`; named rules evaluated in order
- v2: ReBAC relationship graph in `packages/authz-model/`; migrate rule-by-rule
- `AuthzRequest` interface does not change between versions
- Mode is REQUIRED in every `AuthzContext` — same user has different access by mode
- `risk_class` and tool `trust_tier` are different axes — policy function, not ordering

## Consequences
- Policy is testable and auditable (named rules)
- v1→v2 migration is non-breaking (same API, different engine)
- Token audience binding (RFC 8707) enforced for all tokens
