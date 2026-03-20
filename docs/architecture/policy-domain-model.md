# Policy Domain Model

Policy is split into three domains. Do not merge them into one fuzzy `policy` module.

## Three policy domains

| Domain | Scope | Package path | Example rules |
|--------|-------|-------------|---------------|
| **Command policy** | Who may request and approve high-risk actions; what risk class a command has | `packages/policy/command-policy/` | risk_class gates; operator approval thresholds; actuation lockout rules |
| **Assistant policy** | Who may access memory and tools per person and role | `packages/policy/assistant-policy/` | Household role → memory scope mapping; tool tier access per role; privacy rules |
| **Capability policy** | Which assets and actions are reachable under which conditions | `packages/policy/capability-policy/` | Site read-only vs control gates; tool tier (T0–T5) per action; degraded-mode capability restrictions |

## Command policy

Governs the orchestrator's job model. Every job has a `risk_class`:

| risk_class | Approval mode | Example jobs |
|------------|--------------|-------------|
| `INFORMATIONAL` | None | Read sensor value, view asset status |
| `LOW` | Auto-approve (policy) | Fan speed adjustment, set thermostat |
| `MEDIUM` | Auto-approve with audit | Irrigation run, vent cycle |
| `HIGH` | Explicit operator approval | Valve close, pump override, chemical dose |
| `CRITICAL` | Explicit approval + second confirmation | Emergency shutoff, safety relay, drone arm |

Rules:
- `origin: ai_advisory` jobs with `risk_class >= HIGH` always require explicit approval.
- `origin: sensor_rule` jobs with `risk_class >= MEDIUM` require audit; `>= HIGH` require approval.
- `origin: operator` jobs with `risk_class == CRITICAL` require second confirmation.
- No job transitions from `APPROVED` → `EXECUTING` without a logged approval event.

## Assistant policy

Governs memory and tool access per household role.

| Role | Memory access | Tool tier access |
|------|--------------|-----------------|
| `FOUNDER_ADMIN` | personal + household shared + site/system | T0–T4 (never T5) |
| `ADULT_MEMBER` | personal + household shared | T0–T3; site read-only (T3) |
| `CHILD_GUEST` | personal (own) only | T0–T1 |
| `MAINTENANCE_OPERATOR` | site/system only | T0–T3 ops; no household memory |

Rules:
- Private memory is never accessible by another user regardless of role.
- Household shared memory is accessible by all non-guest roles.
- Site/system memory requires MAINTENANCE_OPERATOR or FOUNDER_ADMIN.

## Capability policy

Governs which physical capabilities are reachable per request context.

| Context | Reachable capabilities |
|---------|----------------------|
| Normal ops | All read + MEDIUM and below control |
| Degraded (MQTT down) | Read from Postgres cache only; no new control commands |
| Degraded (Postgres down) | No new jobs; local edge fallback only |
| Emergency mode | Defined subset per emergency-mode-spec.md |

Rules:
- Tool registration auto-inherits capability tier.
- model-router enforces capability policy before any tool call.
- No capability is unlocked at runtime; changes require deployment.

## Implementation

```
packages/policy/
  command-policy/
    risk_class.py         # Enum and thresholds
    approval_rules.py     # Approval mode per origin × risk_class
    audit_requirements.py # When to write audit events
  assistant-policy/
    role_definitions.py   # Role enum and memory scope mapping
    tool_access.py        # Role → tool tier access
    privacy_rules.py      # Private vs shared memory enforcement
  capability-policy/
    capability_registry.py  # Tool → capability tier mapping
    mode_gates.py           # Normal / degraded / emergency capability sets
    tool_tier.py            # T0–T5 enum and enforcement
```

Policy packages are imported by orchestrator (command-policy), model-router (capability-policy), and context-router/assistant-api (assistant-policy). They have no runtime dependencies on each other.
