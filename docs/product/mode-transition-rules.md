# Mode Transition Rules

**Status:** Authoritative  
**Owner:** Product  
**ADR:** ADR-032  
**Contracts:** `packages/runtime-contracts/models.py` — `Mode`, `Surface`, `ExecutionContext`

---

## Purpose

Prevents context blur across users, rooms, devices, and sessions. Without these rules, the same request in a different room or on a different device will receive different privacy guarantees, different tool access, and inconsistent memory behavior.

---

## Mode Enum

```
PERSONAL   — private, individual context; no site tools; no family context leak
FAMILY     — household shared context; limited tool access; child-safe
WORK       — professional context; no household/personal context leak
SITE       — site-control context; full operational tools (T0–T4); operators only
EMERGENCY  — all surfaces override; restricted to emergency-only actions
```

---

## Stickiness Rule

**Mode is sticky per `{user_id × surface}`.**

The same user holds independent modes across surfaces simultaneously.

| User | Surface | Mode |
|------|---------|------|
| founder_001 | voice-gateway:office | WORK |
| founder_001 | family-web | FAMILY |
| founder_001 | ops-web | SITE |
| founder_001 | voice-gateway:kitchen | PERSONAL |
| family_member_002 | family-web | FAMILY |
| guest_003 | any | FAMILY (locked) |

`runtime-kernel` resolves `ExecutionContext.mode` from the surface in the active request. It does not use a global per-user mode.

The sticky map key is: `f"{user_id}:{surface_id}"` where `surface_id` may include device context (e.g., `"voice:kitchen-node-01"`).

---

## Trigger Sources

Mode can change via:

1. **Explicit user command** — `"Switch to work mode"` → context-router → runtime-kernel updates sticky map
2. **Room/device entry** — presence sensor or voice node registration triggers context-router lookup
3. **Time-of-day schedule** — configured in `packages/config/site.yaml`; e.g., FAMILY mode forced 8pm–8am
4. **Emergency event** — any E-stop or security alarm escalation forces EMERGENCY globally
5. **System health event** — MQTT_DOWN forces SITE tools offline; AI_DOWN forces deterministic-only mode

---

## Authority Precedence

```
EMERGENCY (system-wide override) >
OPERATOR explicit command         >
System policy (schedule, config)  >
Surface default                   >
Previous sticky value
```

---

## Mode Isolation (enforced at step 6)

These are authorization rules, not preferences. Enforced by `authz-service` at step 6 via `AuthzContext.mode`.

| Mode | Can access | Cannot access |
|------|-----------|---------------|
| PERSONAL | personal tools, PERSONAL memory | site tools, WORK memory, household actuators |
| FAMILY | household tools, HOUSEHOLD_SHARED memory | WORK memory, PERSONAL memory, site actuators |
| WORK | work tools, WORK memory | PERSONAL memory, site actuators |
| SITE | all tools T0–T4 (founder/operator only) | N/A (full access) |
| EMERGENCY | emergency-only tools | all non-emergency tools |

---

## Child and Guest Lock

- **Child/guest users**: mode is always FAMILY regardless of surface, device, or explicit command.
- Children and guests cannot elevate to PERSONAL, WORK, or SITE mode.
- This is not a preference — it is a hard check in `authz-service`.
- Checked by: `identity-service` role in `AuthzContext`; if role is `CHILD` or `GUEST`, mode is forced to FAMILY.

---

## Multi-Presence Handling

When multiple users are active on different surfaces simultaneously, each surface-request resolves its own `ExecutionContext.mode` independently. There is no global mode state.

Example:
- founder_001 is on ops-web (SITE mode) running a job
- founder_001 also asks kitchen voice a question (PERSONAL mode on that surface)
- Both requests are processed with their respective modes
- Neither bleeds into the other

---

## Shared-Device Ambiguity Rule

When speaker or user identity is **uncertain**, the system MUST default to the lowest safe mode.

**Triggers for uncertain identity:**
- No active authenticated session on the device
- Voice node in a multi-person room with no speaker identification
- Shared kiosk or TV interface
- Voice print confidence below threshold (see `docs/product/voice-fluency-spec.md`)

**Required behavior:**
1. Downgrade to FAMILY low-trust mode
2. Suppress outputs containing PERSONAL, WORK, or SITE-scoped content
3. Do not read PERSONAL or WORK memory
4. Do not invoke tools above T1 (informational only)
5. Require identity confirmation (voice print re-auth, PIN, or app approval) before granting scoped access

**Confirmation flow:**
```
[uncertain identity detected]
       ↓
mode = FAMILY (forced)
       ↓
computer: "I'm not sure who I'm talking to. For personal information, please confirm your identity."
       ↓
[user confirms: voice print / PIN / app]
       ↓
mode = resolved (PERSONAL / WORK based on identity)
```

This rule is implemented in `voice-gateway` (voice print confidence check) and `context-router` (identity certainty field in context resolution).

---

## Emergency Mode

- Triggered by: E-stop event, security alarm, operator emergency command
- Effect: EMERGENCY mode is applied globally across ALL surfaces for ALL users
- Permitted in EMERGENCY: emergency tools only (`emergency.alert`, `emergency.estop`, `emergency.notify`)
- Blocked in EMERGENCY: all household tools, all site control tools, all personal tools
- Revert: only by OPERATOR explicit command via `control-api`

```
[E-stop received]
       ↓
runtime-kernel POST /interrupt → risk_class=CRITICAL, origin=OPERATOR
       ↓
context-router: mode = EMERGENCY for all active surfaces
       ↓
authz-service: only emergency tools allowed
       ↓
attention-engine: INTERRUPT CRITICAL to all relevant audience
```

---

## Mode Change Audit

Every mode change is recorded in `StepAuditRecord` with:
- Previous mode
- New mode
- Trigger source (explicit/schedule/emergency/room/health)
- `mode_change_reason` string in `ExecutionContext`

The operational rubric check "mode continuity" verifies that `ExecutionContext.mode` either matches the surface's sticky mode or has an explicit `mode_change_reason`. A mode change without a reason is a bug.

---

## Related Documents

- `docs/architecture/runtime-kernel.md` — CRK loop; mode at step 3 and step 6
- `docs/architecture/kernel-authority-model.md` — who owns mode resolution
- `docs/product/voice-fluency-spec.md` — speaker identification and voice-confidence rules
- `docs/adr/ADR-032-mode-transitions.md`
