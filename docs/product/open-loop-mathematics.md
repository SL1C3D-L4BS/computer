# Open Loop Mathematics

**Status:** SPECIFIED  
**Owner:** runtime-kernel (continuity processor)  
**Contract type:** `OpenLoop` in `packages/runtime-contracts/models.py`  
**Depends on:** system-state-model.md (Partition 1 — Operational State)

---

## Design Principle

An open loop is not a TODO item. It is a **decaying priority signal**. Without decay, continuity becomes accumulation — an unbounded backlog that destroys trust rather than building it. Every open loop must have a bounded lifetime with defined decay behavior, resurfacing rules, and an abandonment rule.

---

## OpenLoop State Variables

| Field | Type | Scale | Semantics |
|-------|------|-------|-----------|
| `priority_score` | `float` | [0,1] | Initial urgency × importance × recency at creation time |
| `freshness` | `float` | [0,1] | 1.0 at creation; decays toward 0.0 continuously |
| `decay_function` | `str` | enum | Algorithm used: `exponential` \| `linear` \| `step` |
| `decay_half_life_hours` | `float` | hours | For exponential: time to reach freshness=0.5. For linear: hours to reach 0. |
| `closure_conditions` | `list[str]` | — | Event type strings that trigger CLOSED transition |
| `owner_confidence` | `ConfidenceScore` | [0,1] | Certainty of who owns resolution (from identity model) |
| `resurfacing_schedule` | `str` | cron or event | When to attempt resurfacing |
| `max_age_hours` | `float` | hours | Maximum loop age before forced ABANDONED |
| `min_resurfacing_interval_s` | `float` | seconds | Minimum gap between resurfacing attempts |

---

## Priority Score Computation

At creation time:

```python
priority_score = clamp(
    urgency_weight × urgency       # 0.0–1.0, e.g. 0.5
  + importance_weight × importance # 0.0–1.0, e.g. 0.3
  + recency_weight × recency       # 0.0–1.0, e.g. 0.2
, min=0.0, max=1.0)

# Default weights: urgency=0.5, importance=0.3, recency=0.2
# EMERGENCY loops: urgency_weight=0.9, others reduced proportionally
```

`priority_score` is **not updated** over time. It represents the loop's initial importance. The *effective priority* at any point in time is `priority_score × freshness`.

---

## Decay Functions

### Exponential Decay (default for most loops)

```
freshness(t) = exp(-λ × t)

where: λ = ln(2) / decay_half_life_hours
       t = elapsed_hours since loop creation
```

At `t = decay_half_life_hours`: `freshness = 0.5`  
At `t = 3 × decay_half_life_hours`: `freshness ≈ 0.125`  
At `t = 5 × decay_half_life_hours`: `freshness ≈ 0.031`

Recommended defaults by loop category:

| Category | Half-life | Rationale |
|----------|-----------|-----------|
| Reminders (time-critical) | 12h | Stale quickly; must be resolved or abandoned |
| Household tasks | 48h | Family-paced; moderate urgency |
| Work commitments | 72h | Work rhythm; 3-day follow-up window |
| Founder decisions | 24h | High strategic cost of delay |
| Site incidents | 168h (7d) | Long-lived; needs formal closure |

### Linear Decay

```
freshness(t) = max(0.0, 1.0 - t / decay_half_life_hours)
```

Linear decay reaches 0.0 at `t = decay_half_life_hours`. Use for loops with hard deadlines (e.g. time-sensitive approvals).

### Step Decay

```
freshness(t) = 1.0 if t < decay_half_life_hours else 0.0
```

Used for loops that are either fully fresh or fully stale (e.g. "check if update is ready" with a known release window). Transitions abruptly to 0 — forces ABANDONED check.

---

## Resurfacing Rule

Resurfacing is permitted when:

```python
def should_resurface(loop: OpenLoop, attention_threshold: float, now_s: float) -> bool:
    effective_priority = loop.priority_score * loop.freshness
    time_since_last_surfaced = now_s - (loop.last_surfaced_at or 0)

    return (
        effective_priority > attention_threshold
        and time_since_last_surfaced >= loop.min_resurfacing_interval_s
        and loop.status == OpenLoopStatus.ACTIVE
    )
```

**Attention threshold:** 0.15 (configurable per mode). In EMERGENCY mode: 0.0 (all ACTIVE loops resurface on next opportunity). In WORK mode: 0.25 (higher bar to prevent distraction).

**Priority selection:** When multiple loops qualify simultaneously, select the one with highest `priority_score × freshness`. Never resurface more than 1 loop per attention slot.

---

## Abandonment Rule

```python
def should_abandon(loop: OpenLoop, now_s: float) -> bool:
    age_hours = (now_s - loop_created_at_s) / 3600.0
    return (
        loop.freshness < 0.05
        and age_hours > loop.max_age_hours
        and loop.status == OpenLoopStatus.ACTIVE
    )
```

When a loop is abandoned:
1. Status transitions to `ABANDONED`
2. `closed_at` is set to `now()`
3. An `ObservationRecord` with `type = "completion"` and `value = "abandoned"` is written to audit log
4. If `owner_confidence.value > 0.7`, the user is notified once with a summary of what was abandoned

**Invariant I-09:** An ACTIVE loop must never simultaneously have `freshness < 0.05` AND `age_hours > max_age_hours`. The abandonment check runs at minimum every 10 minutes.

---

## Closure Conditions

Loops are closed (transition to `CLOSED`) when any event matching `closure_conditions` is received:

```python
STANDARD_CLOSURE_CONDITIONS = [
    "user.confirmed_resolution",    # User explicitly said "yes, that's done"
    "workflow.completed",           # Bound workflow finished successfully
    "observation.correction",       # User provided a correction that resolves the loop
    "operator.cancelled",           # Operator explicitly cancelled
]
```

Custom closure conditions can reference specific tool invocations, workflow signals, or semantic event types.

**On closure:** `ObservationRecord` with `type = "completion"` and `value = "closed"` is written. The loop remains in `ComputerState` for 24 hours for UX visibility, then is removed from the active projection.

---

## Decay Update Frequency

The continuity processor must:
1. Update `freshness` for all ACTIVE loops every 10 minutes
2. Check abandonment conditions on every update
3. Check resurfacing conditions on every CRK step 8 (attention gate)
4. Emit a `StepAuditRecord` whenever any loop transitions state

---

## Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Open loop closure rate | > accumulation rate | ComputerState audit trail |
| Mean loop age at closure | < 48h for PERSONAL | Audit trail aggregation |
| Abandonment rate | < 10% of created loops | Monthly audit |
| Resurfacing frequency | < 2× per loop per day | ObservationRecord count |
| False abandonment rate | 0% (user disputes) | TrustSignal monitoring |
