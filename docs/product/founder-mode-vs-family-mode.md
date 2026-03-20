# Operating Modes: Founder Mode vs Family Mode

Computer operates in five named modes. Each mode has a distinct primary interface, trust model, and memory scope. Modes are not user roles — roles are assigned once at identity creation; modes are selected per session.

## Mode definitions

| Mode | Primary interface | Trust model | Memory scope | Max tool tier |
|------|-----------------|-------------|-------------|--------------|
| **PERSONAL** | voice, family-web | Private; individual only | Personal only | T3 |
| **FAMILY** | voice, family-web | Household shared; role-based | Household shared | T3 |
| **WORK** | chat (ops-web), family-web | Project context; founder only | Project context | T3 + research |
| **SITE** | ops-web, voice | Read-first; job-based actuation | Site/system | T4 (with approval) |
| **EMERGENCY** | voice, ops-web | Restricted override semantics | Site/system | T4 restricted (see emergency-mode-spec) |

## PERSONAL mode

When to use: Individual tasks — personal reminders, private notes, private calendar, personal research.

Rules:
- No household member can see another's PERSONAL mode interactions or memory.
- Shared household calendar is readable (T0) but only personal calendar entries are writable (T3) in this mode.
- No site control in this mode.
- Can be accessed on voice (mode is inferred from device + user identity) or family-web (explicit mode switch).

## FAMILY mode

When to use: Shared household coordination — groceries, chores, shared calendar, household routines.

Rules:
- All ADULT_MEMBER and FOUNDER_ADMIN users can access household shared memory.
- CHILD/GUEST users in family mode have read access to non-sensitive household info; they cannot write shared memory.
- No site control in this mode.
- Private memory of individual members is not accessible in FAMILY mode even to FOUNDER_ADMIN.

## WORK mode

When to use: Founder/builder tasks — coding, architecture, project planning, SaaS work.

Rules:
- Only FOUNDER_ADMIN has access to WORK mode.
- Memory scope includes project context (separate from personal and household).
- Research tools and external search are available.
- No site control.
- Family and personal memory are not accessible in WORK mode to prevent context bleed.

## SITE mode

When to use: Site operations — monitoring, job approval, incident review, system status.

Rules:
- Available to FOUNDER_ADMIN (full T4) and MAINTENANCE_OPERATOR (T3, read-only site).
- Read-only queries are T3; any control action is T4 and requires orchestrator approval.
- Household and personal memory are not accessible in SITE mode.
- Site mode is the only mode where job proposals (T4) are possible through the assistant.

## EMERGENCY mode

When to use: Active emergencies — leak, fire, intrusion, medical.

Rules:
- See `docs/safety/emergency-mode-spec.md` for full spec.
- EMERGENCY mode unlocks a bounded subset of T4 actions (valve close, safe-stop, land-now).
- Hard limits still apply.
- Requires acknowledgment within 60 seconds if auto-triggered.
- Expires after 30 minutes.

## Mode switching

| Trigger | Resulting mode |
|---------|---------------|
| Voice wakeword in kitchen (default room) | FAMILY |
| Voice wakeword in founder's office | PERSONAL or WORK (configurable) |
| Login to family-web | FAMILY |
| Switch in family-web settings | Any allowed mode for the role |
| Login to ops-web | SITE |
| Emergency voice command | EMERGENCY |
| Sensor rule trigger | EMERGENCY |

Mode switching between PERSONAL ↔ FAMILY ↔ WORK is seamless within a session. Mode switching to SITE or EMERGENCY requires explicit action or event trigger.

## Why modes matter

Without modes, a single conversation can accidentally blend personal reminders, household chores, and site job proposals — creating incorrect memory writes, privacy leaks, and inappropriate tool access. Modes enforce context isolation at the architectural level, not just at the UX level.

context-router always resolves mode before model-router is called. The mode is part of the context envelope and constrains memory scope and max tool tier throughout the entire conversation turn.
