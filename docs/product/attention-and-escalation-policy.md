# Attention and Escalation Policy

**Status:** Authoritative  
**Owner:** Product  
**ADR:** ADR-020 (Attention Plane), ADR-028 (Attention decisions are step 9, not UI)  
**Service:** `services/attention-engine/`

---

## Core Principle

**Attention decisions are part of execution (step 9), not a UI concern.**

The `attention-engine` determines *how* and *when* to deliver the response. The UI layer renders what it receives. This separation ensures consistent interrupt behavior regardless of which surface or component initiates the response.

---

## Interrupt Scoring Formula

```
score = urgency × (1 - attention_load) × privacy_factor × time_weight
```

| Variable | Source | Range |
|----------|--------|-------|
| `urgency` | intent_class + risk_class | 0.0–1.0 |
| `attention_load` | `ComputerState.attention_load` | 0.0–1.0 |
| `privacy_factor` | mode + audience context | 0.0–1.0 |
| `time_weight` | time-of-day + user schedule | 0.0–1.0 |

### Decision Thresholds

```
CRITICAL risk class → always INTERRUPT (formula override)

score ≥ 0.7 → INTERRUPT  Deliver immediately on the primary channel
score ≥ 0.4 → QUEUE      Deliver at the next natural pause or turn
score ≥ 0.2 → DIGEST     Batch into next scheduled summary
score < 0.2 → SILENT     Log only; do not surface to user
```

### Urgency by Risk Class (default mapping)

| Risk Class | Default Urgency |
|-----------|----------------|
| CRITICAL | 1.0 (always override to INTERRUPT) |
| HIGH | 0.8 |
| MEDIUM | 0.5 |
| LOW | 0.3 |

---

## AttentionDecision Schema

```python
@dataclass
class AttentionDecision:
    decision: AttentionAction      # INTERRUPT | QUEUE | DIGEST | SILENT
    channel: Channel               # VOICE | WEB | MOBILE | OPS
    audience: list[str]            # User IDs to notify
    reasoning: str                 # Human-readable scoring explanation
    delay_ms: int = 0             # Delivery delay (0 = immediate)
    priority: AttentionPriority    # CRITICAL | HIGH | NORMAL | LOW
```

This is defined in `packages/runtime-contracts/models.py` and returned in `ResponseEnvelope`.

---

## Channel Resolution

Mode-aware channel mapping:

| Mode | Default Channel |
|------|----------------|
| PERSONAL | VOICE (primary) |
| FAMILY | WEB |
| WORK | WEB |
| SITE | OPS |
| EMERGENCY | OPS (broadcast) |

Override: if INTERRUPT but user is not on a voice-capable device, downgrade to WEB.

---

## Audience Routing

Who receives the attention notification?

| Scenario | Audience |
|----------|---------|
| Personal request | Requesting user only |
| Household event | All active family members |
| Emergency | All users on all active surfaces |
| Contractor site event | Founder/owner only |
| DIGEST | Requesting user at next scheduled summary time |

Audience is set by the `attention-engine` based on mode and event type.  
Runtime-kernel does NOT override audience — attention-engine owns this.

---

## Attention Load

`ComputerState.attention_load` is a 0.0–1.0 float that reflects how "occupied" the system believes the user to be.

Sources that increase attention_load:
- Active voice conversation in progress (0.3+)
- Multiple workflows running simultaneously (0.1 each)
- Recent INTERRUPT in last 60 seconds (0.2)
- Known user schedule: meeting in progress (0.5)

Effect: as `attention_load` approaches 1.0, the interrupt threshold rises. More events are QUEUEd or DIGESTed rather than INTERRUPTed.

---

## Escalation Policy

If a QUEUE or DIGEST item is not acknowledged within its deadline:

```
T+0:        Event → QUEUE (score 0.4–0.69)
T+5min:     No acknowledgment → escalate to INTERRUPT on primary channel
T+15min:    No acknowledgment → notify secondary audience (e.g., other family member)
T+1hr:      Safety-critical items → escalate to emergency contact
```

SILENT items are never escalated.

---

## Failure Semantics

If the `attention-engine` is unreachable or returns an error:
- `runtime-kernel` falls back to `QUEUE NORMAL` on the surface's default channel
- Never halts the execution loop
- Logs: `attention_engine.fallback` event

---

## Examples

| Input | Score | Decision |
|-------|-------|---------|
| E-stop triggered | CRITICAL override | INTERRUPT CRITICAL to OPS |
| "Remind me in 10 min" | urgency=0.3, no load | QUEUE NORMAL |
| "Irrigation job completed" at midnight | time_weight=0.1 | DIGEST |
| Security camera motion alert (night) | urgency=0.7, time=0.5 | INTERRUPT HIGH |
| Calendar event in 5 min | urgency=0.5, attention=0.3 | QUEUE NORMAL |
