# ADR-011: Computer includes a Personal Intelligence Plane separate from Site Operations

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Computer is not only a site operations kernel. It is also a persistent household and personal intelligence for daily life. These are two different product domains with different trust models, UX requirements, memory models, and failure consequences.

If the personal/family assistant is bolted onto the ops kernel as an afterthought, it will inherit ops constraints (risk classes, approval workflows, site-focused UX) that are inappropriate for personal reminders and household coordination.

## Decision

Introduce a **Personal Intelligence Plane** as a first-class product domain, parallel to the site operations kernel.

### Two products in one system

**(A) Computer Core** — orchestrator, digital-twin, control-api, event-ingest, adapters, control services, robotics, perception, audit, policy engine.

**(B) Computer Assistant** — personal/family assistant runtime, identity and household profiles, memory and preference store, calendar/tasks/reminders/notes, family-safe voice and chat UX, household routines, policy-gated household tools.

### Why they are separate

| Dimension | Site Operations | Personal/Family Assistant |
|-----------|----------------|--------------------------|
| Failure consequence | Physical safety | Trust and privacy |
| Memory type | Job/asset/system state | Preferences, routines, household context |
| Users | Operator/admin | All household members |
| UX | Command and review | Conversational and ambient |
| Approval model | Risk-class gated | Implicit for low-risk personal tasks |

## New services introduced

- `apps/assistant-api/` — Conversational API surface
- `services/memory-service/` — Personal and household memory
- `services/identity-service/` — Household members and roles
- `services/context-router/` — Intent and context classification
- `services/assistant-tools/` — Personal productivity and household tools
- `services/routine-engine/` — Household routines

## New packages introduced

- `packages/assistant-contracts/` — Conversation, session, memory, tool schemas
- `packages/persona/` — Persona spec, style rules, escalation rules

## Consequences

- Computer has two product surfaces: ops-web (operators) and family-web + voice (household).
- Shared kernel (orchestrator, MQTT, Postgres) serves both products.
- Trust model is different: Personal Intelligence Plane uses household role + memory scope; ops kernel uses risk class + approval.
- The assistant never becomes an ops proxy; it routes to ops only through control-api with appropriate approval requirements.
