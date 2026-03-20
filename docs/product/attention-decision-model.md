# Attention Decision Model

**Status:** SPECIFIED  
**Owner:** `services/attention-engine/`  
**Contract types:** `AttentionCost`, `DecisionRationale`, `ObservationRecord` in `packages/runtime-contracts/models.py`  
**Depends on:** objective-functions.md (Domain 3), uncertainty-and-confidence-model.md, transition-and-control-model.md (Agent 2)

---

## Design Principle

Attention is a **decision-theoretic problem**, not a scoring heuristic. The current scoring formula (urgency × (1 - attention_load) × privacy_factor × time_weight) is a reasonable first approximation, but it has no concept of expected value, no feedback loop, and no inspectable rationale. This model replaces it with an explicit expected cost/value decision function that is measurable, loggable, and improvable.

---

## Decision Function

```
net_value(action, event, context) =
    urgency_value(event.urgency, context.mode)
  - interruption_cost(context.attention_load, context.cooldown_remaining_s)
  - privacy_risk(event.audience, context.mode, context.identity_confidence)
  + predicted_ack_likelihood(context) × value_of_acknowledgment(event.urgency)
  - time_to_decay_penalty(action, event.urgency_decay_rate)

decision = argmax_{INTERRUPT, QUEUE, DIGEST, SILENT} net_value(action, event, context)
```

All terms are normalized to [0,1] per `measurement-and-scaling-model.md`. `net_value` is unbounded but clipped to [-1, 1] before comparison. A decision with `net_value < 0` means the cost of delivering exceeds the benefit — default to SILENT unless hard-override applies.

---

## Term Definitions

### urgency_value(urgency, mode)

Normalized urgency adjusted for operating mode:

```python
MODE_URGENCY_WEIGHTS = {
    Mode.PERSONAL:   0.8,
    Mode.FAMILY:     0.9,
    Mode.WORK:       0.7,
    Mode.SITE:       1.0,
    Mode.EMERGENCY:  1.5,  # Can produce values > 1.0 before clipping
}
urgency_value = clamp(urgency × MODE_URGENCY_WEIGHTS[mode], 0.0, 1.0)
```

### interruption_cost(attention_load, cooldown_remaining_s)

```python
cooldown_factor = min(1.0, cooldown_remaining_s / MAX_COOLDOWN_S)
interruption_cost = attention_load × 0.7 + cooldown_factor × 0.3
```

High attention load + active cooldown → cost approaches 1.0. Idle user with no cooldown → cost approaches 0.0.

### privacy_risk(audience, mode, identity_confidence)

```python
base_risk = PRIVACY_RISK_BY_MODE[mode]
# PERSONAL: 0.1, FAMILY: 0.3, WORK: 0.2, SITE: 0.1, EMERGENCY: 0.0
identity_uncertainty_premium = (1.0 - identity_confidence) × 0.5
privacy_risk = clamp(base_risk + identity_uncertainty_premium, 0.0, 1.0)
```

Unknown identity on a shared device in FAMILY mode → risk = 0.3 + 0.5 = 0.8. This effectively prevents INTERRUPT.

### predicted_ack_likelihood(context)

Estimated from attention memory:

```python
def predicted_ack_likelihood(context: AttentionContext, memory: AttentionMemory) -> float:
    base = BASE_ACK_LIKELIHOOD[context.mode]  # PERSONAL: 0.6, FAMILY: 0.5, WORK: 0.4
    history_modifier = compute_history_modifier(
        prior_surfacings=memory.prior_surfacings_count,
        prior_dismissal_rate=memory.prior_dismissal_rate,
        escalation_rate=memory.escalation_rate,
    )
    return clamp(base + history_modifier, 0.05, 0.95)
```

`history_modifier` is in range [-0.4, +0.4]:
- High prior dismissal rate → strong negative modifier
- Prior escalation → positive modifier
- Many prior surfacings without closure → negative modifier

### value_of_acknowledgment(urgency)

```python
value_of_acknowledgment = urgency × 0.8 + 0.2
# Ranges from 0.2 (no urgency) to 1.0 (maximum urgency)
# The 0.2 floor ensures even low-urgency acks have some value
```

### time_to_decay_penalty(action, urgency_decay_rate)

```python
EFFECTIVE_DELAYS = {
    AttentionAction.INTERRUPT: 0,
    AttentionAction.QUEUE:     300,   # 5 min average
    AttentionAction.DIGEST:    3600,  # 1 hr average
    AttentionAction.SILENT:    86400, # 24 hr — effectively never
}
delay_s = EFFECTIVE_DELAYS[action]
decay_penalty = 1.0 - exp(-urgency_decay_rate × delay_s)
```

High `urgency_decay_rate` (urgent, time-sensitive events) → DIGEST and SILENT have large penalties. Low decay rate (background info) → delay is cheap.

---

## Suppression State Machine

The suppression state machine prevents attention fatigue from repeated INTERRUPT decisions.

```
State: NORMAL
  → [INTERRUPT decision emitted] → SUPPRESSED(cooldown_ms)
  → [3× same event QUEUED without ack] → ESCALATION_PENDING

State: SUPPRESSED(cooldown_ms)
  → [cooldown timer expires] → NORMAL
  → [new event with risk_class = CRITICAL] → FORCE_INTERRUPT (bypasses suppression)
  → [new event with risk_class = HIGH and urgency > 0.85] → FORCE_INTERRUPT

State: ESCALATION_PENDING
  → [next event of same type received] → INTERRUPT (forced)
  → [closure event received] → NORMAL
```

**Cooldown policy by mode:**

| Mode | Default cooldown after INTERRUPT |
|------|----------------------------------|
| PERSONAL | 120s |
| FAMILY | 180s |
| WORK | 300s |
| SITE | 60s |
| EMERGENCY | 0s (no cooldown) |

---

## Alert Clustering

When multiple events of the same type arrive within a time window, they should be batched into a single DIGEST rather than triggering multiple INTERRUPT/QUEUE decisions.

```python
def should_cluster(event: Event, pending_events: list[Event], window_s: float = 300) -> bool:
    similar = [e for e in pending_events
               if event_similarity(e, event) > 0.7
               and abs(e.timestamp - event.timestamp) < window_s]
    return len(similar) >= 2

def cluster_to_digest(events: list[Event]) -> Event:
    # Combine into single summary event with max urgency
    return Event(
        urgency=max(e.urgency for e in events),
        content=f"{len(events)} similar events: {summarize(events)}",
        urgency_decay_rate=min(e.urgency_decay_rate for e in events),
    )
```

**Clustering does not apply to CRITICAL risk events.** Each CRITICAL event is evaluated independently regardless of clustering.

---

## Acknowledgment Feedback Update

Every user response to an attention decision is recorded as an `ObservationRecord` and used to update `AttentionMemory`:

```python
def process_observation(obs: ObservationRecord, memory: AttentionMemory) -> AttentionMemory:
    if obs.observation_type == ObservationType.ACKNOWLEDGMENT:
        memory.ack_count += 1
        memory.prior_dismissal_rate = rolling_update(memory.prior_dismissal_rate, 0.0)
        # Positive signal: predicted_ack_likelihood modifier becomes slightly more positive
    elif obs.observation_type == ObservationType.DISMISSAL:
        memory.dismissal_count += 1
        memory.prior_dismissal_rate = rolling_update(memory.prior_dismissal_rate, 1.0)
    elif obs.observation_type == ObservationType.SILENCE:
        # No response within timeout: treat as weak negative signal
        memory.prior_dismissal_rate = rolling_update(memory.prior_dismissal_rate, 0.5)
    elif obs.observation_type == ObservationType.ESCALATION:
        memory.escalation_rate = rolling_update(memory.escalation_rate, 1.0)
    return memory
```

Rolling update uses exponential moving average with α=0.1 (recent observations count more).

---

## AttentionMemory Structure

```python
@dataclass
class AttentionMemory:
    user_id:                str
    event_type_key:         str           # e.g. "irrigation.alert" | "security.motion"
    prior_surfacings_count: int           # How many times this type was surfaced
    prior_dismissal_rate:   float         # [0,1] EMA of dismissals
    escalation_rate:        float         # [0,1] EMA of escalations
    ack_count:              int
    last_surfaced_at:       float         # Epoch seconds
    cooldown_remaining_s:   float         # Remaining suppression time
    suppression_state:      str           # NORMAL | SUPPRESSED | ESCALATION_PENDING
    updated_at:             str           # ISO 8601
```

AttentionMemory is keyed by `(user_id, event_type_key)`. It is persisted in Redis with TTL=7 days. On TTL expiry, the user reverts to base priors.

---

## DecisionRationale at Step 9

Every attention decision must produce a `DecisionRationale`:

```python
rationale = DecisionRationale(
    decision=decision.value,
    inputs={
        "urgency": event.urgency,
        "attention_load": ctx.attention_load,
        "identity_confidence": ctx.identity_confidence,
        "mode": ctx.mode.value,
        "prior_dismissal_rate": memory.prior_dismissal_rate,
        "cooldown_remaining_s": memory.cooldown_remaining_s,
    },
    confidence=effective_confidence,
    objective_weights={"urgency_value": 1.0, "interruption_cost": -1.0, "privacy_risk": -1.0},
    constraints_checked=["HC-01"],   # privacy preservation checked
    hard_constraints_violated=[],
    alternatives_considered=[a.value for a in AttentionAction],
    decided_at=now_iso(),
)
```

This rationale is logged to the audit trail alongside the `AttentionCost` breakdown.

---

## Calibration Target

| Metric | Target |
|--------|--------|
| Brier score (`predicted_ack_likelihood` vs actual) | < 0.25 |
| False escalation rate (INTERRUPT when QUEUE correct) | < 0.05 |
| False silence rate (SILENT when INTERRUPT correct) | < 0.01 |
| Dismissal rate on INTERRUPT decisions | < 0.15 |
| Alert clustering effectiveness | > 30% reduction in total INTERRUPT count on burst scenarios |
