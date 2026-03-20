# Attention Memory Model

**Status:** SPECIFIED  
**Owner:** `services/attention-engine/`  
**Contract types:** `AttentionCost`, `DecisionRationale`, `ObservationRecord` in runtime-contracts  
**Depends on:** attention-decision-model.md, uncertainty-and-confidence-model.md  
**Implementation:** `services/attention-engine/attention_engine/memory.py`, `decision.py`

---

## Why Attention Needs Memory

The current attention-engine is stateless — it scores each event independently. This produces two failure modes:

1. **Attention fatigue:** The same type of alert fires repeatedly because no cooldown exists. Users start ignoring alerts.
2. **Missed escalation:** The user has seen this alert 4 times and dismissed it. On the 5th occurrence it should escalate, but stateless scoring doesn't know that.

`AttentionMemory` stores per-user, per-event-type state that enables the suppression state machine and acknowledgment feedback loop.

---

## AttentionMemory Structure

```python
@dataclass
class AttentionMemory:
    user_id:                str
    event_type_key:         str           # e.g. "irrigation.alert" | "security.motion"
    prior_surfacings_count: int = 0       # How many times surfaced in recent window
    prior_dismissal_rate:   float = 0.0  # [0,1] EMA of dismissal responses
    escalation_rate:        float = 0.0  # [0,1] EMA of escalation responses
    ack_count:              int = 0       # Total acknowledgments (positive signal)
    last_surfaced_at:       float = 0.0  # Epoch seconds; 0 = never
    cooldown_remaining_s:   float = 0.0  # Remaining suppression seconds
    suppression_state:      str = "NORMAL"  # NORMAL | SUPPRESSED | ESCALATION_PENDING
    updated_at:             str = ""     # ISO 8601
```

**Persistence:** Redis with TTL=7 days. Key: `attn:memory:{user_id}:{event_type_key}`  
**On TTL expiry:** User reverts to base priors (dismissal_rate=0, escalation_rate=0, cooldown=0)

---

## Suppression State Machine

States and transitions control whether an alert can fire immediately:

```
NORMAL
  ├─[INTERRUPT decision emitted]──────────────► SUPPRESSED(cooldown_s)
  └─[same type QUEUEd ×3, no ack]─────────────► ESCALATION_PENDING

SUPPRESSED(cooldown_s)
  ├─[cooldown_s reaches 0]────────────────────► NORMAL
  ├─[new CRITICAL event arrives]──────────────► FORCE_INTERRUPT (one-shot bypass)
  └─[new HIGH event, urgency > 0.85]──────────► FORCE_INTERRUPT (one-shot bypass)

ESCALATION_PENDING
  ├─[next event of same type]─────────────────► INTERRUPT (forced, bypasses net_value)
  └─[closure event received]──────────────────► NORMAL
```

FORCE_INTERRUPT does not reset the cooldown — the state returns to SUPPRESSED after the forced interrupt.

**Cooldown defaults by mode:**

| Mode | Cooldown after INTERRUPT |
|------|--------------------------|
| PERSONAL | 120s |
| FAMILY | 180s |
| WORK | 300s |
| SITE | 60s |
| EMERGENCY | 0s |

---

## Observation Feedback Loop

Every user response to an attention decision updates `AttentionMemory`:

```python
ROLLING_ALPHA = 0.1  # Recent observations count more

def process_observation(obs: ObservationRecord, memory: AttentionMemory) -> AttentionMemory:
    match obs.observation_type:
        case ObservationType.ACKNOWLEDGMENT:
            memory.ack_count += 1
            memory.prior_dismissal_rate = ema(memory.prior_dismissal_rate, 0.0, ROLLING_ALPHA)
        case ObservationType.DISMISSAL:
            memory.dismissal_count += 1
            memory.prior_dismissal_rate = ema(memory.prior_dismissal_rate, 1.0, ROLLING_ALPHA)
        case ObservationType.SILENCE:
            # Weak negative signal
            memory.prior_dismissal_rate = ema(memory.prior_dismissal_rate, 0.5, ROLLING_ALPHA)
        case ObservationType.ESCALATION:
            memory.escalation_rate = ema(memory.escalation_rate, 1.0, ROLLING_ALPHA)
        case ObservationType.CORRECTION:
            # User corrected the attention decision — strong negative signal
            memory.prior_dismissal_rate = ema(memory.prior_dismissal_rate, 1.0, ROLLING_ALPHA * 3)
    memory.updated_at = now_iso()
    return memory
```

---

## Alert Clustering

When multiple similar events arrive within a time window, they are batched into a DIGEST rather than causing repeated INTERRUPTs:

```python
CLUSTER_WINDOW_S = 300       # 5-minute clustering window
CLUSTER_SIMILARITY_THRESHOLD = 0.7  # Events must be ≥ 70% similar to cluster

def should_cluster(event: Event, pending: list[Event]) -> bool:
    similar = [e for e in pending
               if event_similarity(e, event) > CLUSTER_SIMILARITY_THRESHOLD
               and abs(e.timestamp - event.timestamp) < CLUSTER_WINDOW_S]
    return len(similar) >= 2

def cluster_events(events: list[Event]) -> Event:
    """Merge similar events into a single DIGEST with max urgency."""
    return Event(
        urgency=max(e.urgency for e in events),
        content=f"{len(events)} similar events: {summarize(events)}",
        urgency_decay_rate=min(e.urgency_decay_rate for e in events),
        event_type=events[0].event_type,
        clustered=True,
        cluster_count=len(events),
    )
```

**Clustering does not apply to CRITICAL risk events.** Each CRITICAL event is always evaluated independently.

---

## Implementation Architecture

Three modules in `services/attention-engine/attention_engine/`:

### `memory.py`

- `AttentionMemory` dataclass
- `load_memory(user_id, event_type_key) -> AttentionMemory`
- `save_memory(memory: AttentionMemory) -> None`
- `process_observation(obs: ObservationRecord, memory: AttentionMemory) -> AttentionMemory`
- `update_cooldown(memory: AttentionMemory, elapsed_s: float) -> AttentionMemory`

### `decision.py`

- `compute_attention_cost(event, ctx, memory) -> AttentionCost` — implements the net_value formula
- `make_decision(cost: AttentionCost, memory: AttentionMemory) -> AttentionDecision` — applies suppression state machine
- `build_decision_rationale(decision, event, ctx, cost, memory) -> DecisionRationale`

### `clustering.py`

- `AlertClusterer` — maintains sliding window of pending events
- `cluster_if_needed(event, clusterer) -> Event` — returns original or clustered event

---

## Logging Requirements

Every call to `evaluate` endpoint must emit to audit log:
1. `AttentionCost` — full breakdown of the net_value computation
2. `DecisionRationale` — why this decision was chosen
3. `ObservationRecord` on user feedback (via separate feedback endpoint)

All three must be present in the audit trail for calibration tests to pass.

---

## Calibration Targets

| Metric | Target | Test |
|--------|--------|------|
| Brier score on `predicted_ack_likelihood` | < 0.25 | `test_attention_calibration.py` |
| False escalation rate | < 0.05 | `test_attention_calibration.py` |
| Dismissal rate on INTERRUPT | < 0.15 | ObservationRecord replay |
| Alert clustering effectiveness | ≥ 30% reduction in INTERRUPT count on burst | Clustering unit tests |
| Suppression cooldown accuracy | ±5s of specified cooldown | `test_loop_decay_sanity.py` |
