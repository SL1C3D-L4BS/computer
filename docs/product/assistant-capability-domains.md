# Assistant Capability Domains

Computer's assistant capabilities are organized into six domains. Each domain has explicit responsibilities, available tools, and trust tier boundaries.

## Domain 1 — Personal Executive

Primary users: FOUNDER_ADMIN, ADULT_MEMBER (own context only)

| Capability | Trust tier | Tools |
|-----------|-----------|-------|
| Reminders and alarms | T3 | reminder-tool |
| Task and to-do management | T3 | task-tool |
| Personal calendar (read) | T0 | calendar-read-tool |
| Personal calendar (write) | T3 | calendar-write-tool |
| Personal notes | T3 | notes-tool |
| Work briefings | T0/T1 | briefing-tool, memory-read |
| Research and web search | T0 | search-tool |
| Coding help and architecture memory | T0/T1 | code-tool, memory-read |
| Personal scheduling | T3 | calendar-write-tool, task-tool |

Memory scope: PERSONAL only.

## Domain 2 — Family Coordinator

Primary users: All household members with appropriate roles

| Capability | Trust tier | Tools |
|-----------|-----------|-------|
| Shared household calendar | T0 (read) / T3 (write) | calendar-read-tool, calendar-write-tool |
| Grocery and shopping list | T3 | shopping-tool |
| Household chores and tasks | T3 | chores-tool, task-tool |
| Family reminders | T3 | reminder-tool |
| Shared household notes | T3 | notes-tool |
| Meal planning | T1/T3 | meal-plan-tool |
| Household routine management | T3 (run) / T2 (create) | routine-engine-tool |

Memory scope: HOUSEHOLD_SHARED. PERSONAL memory never visible in this domain.

## Domain 3 — Home Intelligence

Primary users: FOUNDER_ADMIN, ADULT_MEMBER

| Capability | Trust tier | Tools |
|-----------|-----------|-------|
| Energy status query | T0 | energy-status-tool |
| Comfort status (temperature, humidity) | T0 | sensor-query-tool |
| Home routine triggers | T3 (pre-registered) | routine-engine-tool |
| Low-risk home actions (lights, thermostat setpoint) | T3 | home-action-tool |
| Notification and alert review | T0 | incident-query-tool |

These are the only home actions available without going through the ops orchestrator. Any action involving water, power, chemical, or structural systems routes to Domain 4 (Site Operations) and requires T4 approval.

## Domain 4 — Site Operations

Primary users: FOUNDER_ADMIN only (ADULT_MEMBER: read-only T0/T3)

| Capability | Trust tier | Tools |
|-----------|-----------|-------|
| Site status query (read-only) | T0/T3 | site-status-tool, control-api read |
| Asset map query | T0 | digital-twin-query-tool |
| Job status and history | T0 | job-query-tool |
| Greenhouse and energy briefing | T0 | ops-briefing-tool |
| Propose a site job | T1/T4 | job-proposal-tool → control-api → orchestrator |
| Approve a pending job | T4 | job-approval-tool (FOUNDER_ADMIN only) |
| Incident queue review | T0 | incident-query-tool |

Job proposals from the assistant go through control-api → orchestrator approval flow. The assistant never dispatches jobs directly.

## Domain 5 — Builder/Founder Copilot

Primary users: FOUNDER_ADMIN (Work mode)

| Capability | Trust tier | Tools |
|-----------|-----------|-------|
| Coding assistance | T0 | code-tool |
| Architecture memory and ADR lookup | T0 | memory-read, doc-search-tool |
| Repository context | T0 | repo-context-tool |
| Work task management | T3 | task-tool |
| SaaS planning and business notes | T3 | notes-tool, memory-write |
| Technical research | T0 | search-tool |
| Runbook lookup | T0 | doc-search-tool |

This domain requires WORK mode. Memory scope includes project context (separate from personal and household).

## Domain 6 — Safety/Security Sentinel

Primary users: FOUNDER_ADMIN (any mode that permits site access)

| Capability | Trust tier | Tools |
|-----------|-----------|-------|
| Security alert summary | T0 | incident-query-tool |
| Incident escalation | T2/T3 | notification-tool |
| Threat assessment | T0/T1 | osint-query-tool, incident-query-tool |
| Verification requests | T2 | notification-tool |
| Emergency mode trigger | T4 | emergency-trigger-tool (FOUNDER_ADMIN only) |

This domain has **no autonomous response**. The sentinel informs, summarizes, and escalates. Any physical response requires T4 through Site Operations domain.

## Cross-domain routing

When a request spans domains (e.g., "remind me tomorrow and also check greenhouse humidity"), context-router identifies the composite intent and model-router executes tools from the appropriate domains in sequence, each within its tier limits.

Domain escalation (e.g., a Family Coordinator request that triggers a Site Operations job) requires explicit confirmation and the higher tier's approval requirements apply.
