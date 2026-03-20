# ADR-015: Family assistant UX is separate from ops-web

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

ops-web is designed for operators: job consoles, incident queues, asset maps, approval workflows, simulation dashboards. It assumes technical context and operator intent. Family members (adults, children, guests) should not need to navigate ops-web to set a reminder or view the household calendar.

## Decision

Family assistant UX lives in `apps/family-web/` — a separate Next.js application from `apps/ops-web/`.

### family-web surfaces

- Household conversation (voice and text)
- Reminders and tasks (personal and shared)
- Shared household calendar
- Grocery and shopping list
- Household notes
- Chore assignments
- Household routine management
- **Approvals queue**: pending HIGH/CRITICAL jobs from orchestrator, visible and actionable by FOUNDER_ADMIN
- Site status cards (read-only summaries for all household members)

### What family-web does NOT include

- Job console (detailed job management) — ops-web
- Incident queue (security events) — ops-web
- Asset map (full site topology) — ops-web
- Simulation dashboard — ops-web
- Command approval UI (detailed) — ops-web (family-web has simplified approvals)

### Shared components

`packages/ui/` contains shared UI components used by both ops-web and family-web. Authentication uses identity-service; family-web uses household role auth, not admin-only auth.

## Consequences

- Household members use family-web; operators use ops-web.
- FOUNDER_ADMIN uses both depending on context (family tasks in family-web; site management in ops-web).
- family-web is a first-class product; it is not an afterthought added after robotics phases.
- family-web ships in Phase E2 (capability) and Phase H (voice interfaces); both phases are prioritized above Phase F (rover) in terms of assistant capability completeness.
