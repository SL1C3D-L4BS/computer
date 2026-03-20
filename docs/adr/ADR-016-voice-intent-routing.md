# ADR-016: Voice interactions route by intent class

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Voice is an ambient, always-on interface. Without intent routing, a household member saying "turn off the water" could accidentally trigger a site control action. Voice requests span the full range from personal reminders to high-risk site commands, and the system must classify and route them correctly before any tool execution.

## Decision

Every voice interaction is routed through context-router's intent classification before any tool is called. Intent routing happens **before** model-router and **before** tool execution.

### Four intent classes

| Class | Examples | Execution path |
|-------|---------|---------------|
| `PERSONAL` | "Remind me to call mom" | assistant-tools only (T3) |
| `HOUSEHOLD` | "Add milk to the list" | assistant-tools household scope (T3) |
| `SITE_OPS` | "What's the greenhouse humidity?" | control-api read-only query (T3) |
| `HIGH_RISK_CONTROL` | "Open the north valve" | Job proposal → approval required (T4) |

### Routing rules for ambiguous voice requests

1. Default to the **least privileged interpretation** when ambiguous.
2. Ask one clarifying question, not multiple.
3. Never auto-escalate a PERSONAL request to SITE_OPS without explicit user confirmation.
4. HIGH_RISK_CONTROL requests in voice: always confirm explicitly ("I'll submit a request to open the north valve. This requires your approval in ops-web. Do you want me to submit it?").

### Device location context

context-router uses `device_id` (passed by voice-gateway) and a device-location map (in identity-service) to determine the likely operating mode:
- Kitchen/living room devices → FAMILY mode by default
- Founder's office device → PERSONAL or WORK mode by default
- Greenhouse or field devices → SITE mode by default

## Consequences

- Voice cannot be used to trigger HIGH_RISK_CONTROL actions directly; it can only submit job proposals.
- The clarification step for ambiguous commands may feel slightly slower, but prevents misactuation.
- Device location mapping is configured in identity-service; it is not hardcoded.
- All intent classifications are logged for auditability and system improvement.
