# Emergency Mode Specification

Emergency mode is a tightly-scoped operating state. It is **not** a power-user shortcut. Without hard boundaries, it becomes a loophole that bypasses every safety gate.

## Who can trigger emergency mode

| Actor | Method | Verification required |
|-------|--------|----------------------|
| FOUNDER_ADMIN | ops-web → Emergency panel | Identity confirmation (session auth) |
| FOUNDER_ADMIN | voice command: "Computer, emergency" | Voice + PIN confirmation |
| Automated sensor rule | Configured sensor threshold breach | Auto-trigger with immediate audit; operator must acknowledge within 60s |

No other role may trigger emergency mode. ADULT_MEMBER and below cannot trigger it directly; they can request it (which pages the FOUNDER_ADMIN).

## What emergency mode unlocks

Emergency mode unlocks a **predefined, bounded subset** of actions. It does not unlock all capabilities.

| Capability unlocked | Condition |
|--------------------|-----------|
| Immediate valve close (leak isolation) | Any FOUNDER_ADMIN or sensor rule |
| Emergency ventilation | Any FOUNDER_ADMIN |
| Grid power disconnect (load shed) | FOUNDER_ADMIN + explicit confirmation |
| Fire suppression activation | FOUNDER_ADMIN + explicit confirmation |
| Rover safe-stop and return-to-dock | Any FOUNDER_ADMIN |
| Drone land-now command | Any FOUNDER_ADMIN |

These are the ONLY unlocked actions. Emergency mode does not unlock arbitrary actuation.

## What emergency mode still forbids

These are forbidden regardless of emergency mode:

- AI-driven autonomous actuation without a logged human trigger event
- Drone arm or launch from emergency mode (requires normal ops flow)
- Chemical dosing overrides above calibrated limits
- MQTT wildcard publish from any AI path
- Bypassing command_log write
- Disabling device identity enforcement

## Timeout and reset behavior

- Emergency mode automatically expires after **30 minutes** unless explicitly extended.
- Extension requires a re-confirmation from FOUNDER_ADMIN.
- Maximum continuous emergency mode duration: **4 hours** without a full reset.
- After expiration, the system returns to the mode that was active before emergency.
- All jobs created during emergency mode are tagged `origin: emergency` in the audit log.

## Audit requirements in emergency mode

Every action taken during emergency mode:
1. Writes a `job` record with `origin: emergency` and `triggered_by: {user_id | sensor_rule_id}`.
2. Writes a `command_log` entry with timestamp, actor, action, and outcome.
3. Generates an incident summary in the incident queue for operator review.
4. Sends an immediate notification to all FOUNDER_ADMIN users.

Emergency mode cannot be used without full audit. The system must refuse to enter emergency mode if Postgres is down (no audit available).

## Implementation

```python
# apps/orchestrator/emergency_mode.py

class EmergencyModeState:
    active: bool
    triggered_by: str       # user_id or sensor_rule_id
    triggered_at: datetime
    trigger_method: str     # "ops_web" | "voice" | "sensor_rule"
    expires_at: datetime    # triggered_at + 30 min
    extension_count: int
    allowed_actions: list[str]  # from ALLOWED_EMERGENCY_ACTIONS registry

ALLOWED_EMERGENCY_ACTIONS = [
    "valve.close",
    "ventilation.emergency_open",
    "power.grid_disconnect",
    "rover.safe_stop",
    "rover.return_to_dock",
    "drone.land_now",
]
```

Emergency mode state is stored in Redis (ephemeral) and mirrored to Postgres on entry and exit.

## Operator acknowledgment flow

When sensor rule triggers emergency mode automatically:
1. System enters emergency mode, performs the triggered action, writes full audit.
2. Operator receives immediate notification (push + ops-web alert).
3. Operator must acknowledge within **60 seconds** or system plays a verbal alert ("Emergency mode active, please acknowledge").
4. If no acknowledgment in 5 minutes, system sends escalation notification.
5. Emergency mode continues regardless, but unacknowledged emergency events are flagged for review.

## Related documents

- `docs/architecture/policy-domain-model.md` — capability policy in emergency mode
- `docs/safety/actuation-policy.md` — general actuation rules
- `docs/safety/degraded-mode-spec.md` — behavior when infrastructure is degraded
