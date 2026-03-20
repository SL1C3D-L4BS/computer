# Drift Remediation Policy

**Status:** Active  
**Version:** 1.0.0  
**Owner:** AI eval lead (overall); per-monitor owners as specified

---

## Purpose

When a drift alarm fires, this document is the source of truth for what happens next. Every alarm has an owner, a response procedure, and a remediation path. Unowned alarms are treated as severity-1 by default.

---

## Weekly Drift Review Ritual

**Cadence:** Monday morning, every week without exception.

**Command:** `computer drift digest --period 7d`

**Participants:** Founder + named monitor owners

**Purpose:** Without the ritual, drift alerts decay into ignored logs. The ritual ensures that every alarm is acknowledged, every override is reviewed, and every unresolved anomaly has an owner.

**Ritual steps:**
1. Run `computer drift digest --period 7d`
2. Review all alarms fired in the past 7 days
3. For each unresolved alarm: confirm owner, confirm remediation plan, set deadline
4. For each override used: confirm override was valid; check cooldown was respected
5. Check `decision_load_index` trend via `computer founder load`
6. File a brief status note in the drift log (text file or structured record)

---

## Per-Monitor Response Procedures

### `confidence_miscalibration`
**Threshold:** Brier score > 0.25 in any decision class  
**Owner:** AI eval lead  
**Override cooldown:** 48h  

When this fires:
1. Pull all decisions in the affected class from the past 72h via `computer trace`
2. Check whether a recent policy change or model change correlates with the Brier score increase
3. If correlated: rollback the policy change using `computer replay` to confirm
4. If no clear cause: reduce confidence threshold for affected class by 0.05 (conservative mode)
5. Document in `docs/delivery/field-truth-and-shadow-mode.md` divergence log
6. Resolution: Brier score below threshold for 48h in affected class

**Auto-reversion:** If Brier score > 0.35 for 6h, attention engine automatically reverts to conservative confidence thresholds for affected class.

---

### `attention_fatigue`
**Threshold:** `interrupt_dismissal_rate` > 0.30 averaged over 24h  
**Owner:** Attention-engine owner  
**Override cooldown:** 24h  

When this fires:
1. Run `computer trust report` to confirm sustained dismissal rate
2. Review `computer trace` for the top dismissed interrupts — check urgency_decay_rate calibration
3. Increase minimum net_value threshold for INTERRUPT decisions by 10% temporarily
4. If rate normalizes within 24h: calibration fix confirmed; file adjustment as `CandidatePolicyAdjustment`
5. If rate persists: escalate to founder for attention policy review

**Auto-reversion:** If `interrupt_dismissal_rate` > 0.50 for 4h, attention engine switches to DIGEST-only mode (no new INTERRUPT decisions) until manually unlocked.

---

### `memory_growth`
**Threshold:** Open loop count growth > 5%/day for 3 consecutive days without closure  
**Owner:** Memory-service owner  
**Override cooldown:** 72h  

When this fires:
1. Run `computer memory audit` to identify the fastest-growing scopes
2. Check whether new loop creation is being triggered by a misconfigured reflection cycle
3. Run `computer memory audit --gc` to identify stale abandonment candidates
4. Review loops with `freshness < 0.1` — if > 10% of active loops are below this threshold, trigger forced abandonment review
5. Resolution: growth rate below 5%/day for 3 consecutive days

**Auto-reversion:** If loop count exceeds `max_active_loops` invariant (I-09), memory-service automatically archives loops in freshness order (lowest first) until below threshold.

---

### `auth_denial_spike`
**Threshold:** Auth denial rate > 3x rolling 7-day baseline in any 24h window  
**Owner:** Security/identity owner  
**Override cooldown:** 12h  

When this fires:
1. Check audit log for denial patterns: which resource types, which subjects, which modes
2. If pattern is a single user/service: investigate credential rotation or token expiry
3. If pattern is broad: check for identity-service degradation or config change
4. If denial rate > 10x baseline for 1h: initiate incident response; page security owner
5. Resolution: denial rate below 2x baseline for 4h

**Auto-reversion:** None (auth is always enforced). System does not degrade auth checks even under spike. The spike is always investigated, not bypassed.

---

## System Downgrade Behavior

When a drift alarm has been active for more than its remediation deadline without resolution:

| Duration without resolution | System behavior |
| --- | --- |
| > 24h | Conservative mode: reduce attention interrupt rate by 30% |
| > 48h | Founder receives decision_load_index alert; briefing frequency increases |
| > 72h | Founder-only mode: non-founder requests routed to DIGEST until resolved |

Conservative mode is a temporary operational downgrade, not a permanent policy change. It is reversed automatically when the monitor returns to healthy range.

---

## Drift Log Record Format

Every alarm event, override, and resolution must be logged as a structured record:

```python
DisturbanceRecord(
    disturbance_id=<uuid>,
    monitor_name=<str>,
    alarm_type="drift_alarm" | "drift_override" | "drift_resolved",
    threshold_value=<float>,
    observed_value=<float>,
    owner=<str>,
    action_taken=<str>,
    override_reason=<str | None>,
    resolved_at=<iso8601 | None>,
    timestamp=<iso8601>,
)
```

---

## Escalation Path

1. Monitor owner takes action (per procedure above)
2. If unresolved after cooldown: AI eval lead escalates to founder
3. If unresolved after 72h: severity-1 review with all named owners
4. If auto-reversion triggered and does not resolve: production incident
