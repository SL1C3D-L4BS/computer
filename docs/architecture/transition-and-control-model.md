# Transition and Control Model

**Status:** SPECIFIED  
**Authority:** runtime-kernel  
**Depends on:** system-state-model.md, uncertainty-and-confidence-model.md  
**ADR refs:** ADR-019 (CRK binding), ADR-020 (authorization graph), ADR-021 (attention plane)

---

## Purpose

The CRK execution loop and all embedded workflows are **control systems**. This document expresses them as formal transition systems so that transitions can be verified, tested, and reasoned about rigorously. Using control-theoretic framing forces every component to declare what it *measures* (observations) versus what it *assumes* (which leads to hidden heuristics).

---

## Formal Structure

For each agent, define:

- **X** — State (what the agent knows at decision time)
- **U** — Control inputs (what triggers a transition)
- **Y** — Observations (what the agent can actually measure)
- **W** — Disturbances (exogenous noise the agent cannot control)
- **f(X, U, W)** — Transition function
- **h(X)** — Output/decision function

---

## Agent 1: Runtime Kernel (CRK Loop)

**X:** `(mode_by_surface, active_workflow_ids, attention_load, system_health_flags, current_step)`

**U:** `InputEnvelope` (any surface); interrupt signals from orchestrator

**Y:** 
- Step outputs from each service (authz result, attention decision, workflow binding, tool result)
- Service health probe responses

**W:**
- Service unavailability (authz down, memory timeout)
- Concurrent requests from multiple surfaces
- Mode conflicts on shared devices

**Transition types:**

| Transition | Class | Trigger |
|------------|-------|---------|
| Step N → Step N+1 | Deterministic | Step N returns status `ok` |
| Step N → `DEGRADED` | Stochastic | Service health below threshold |
| EMERGENCY escalation | Exogenous | Safety incident detected via MQTT |
| Mode change | Deterministic | Identity confidence crosses threshold |

**f(X, U, W):** `new_ctx = enrich(ctx, step_output)` — each step returns an enriched `ExecutionContext`. No step may mutate the existing context object.

---

## Agent 2: Attention Engine

**X:**
```
(
  prior_surfacings: int,           # How many times this event type was surfaced in window
  last_dismissed_at: float | None, # Epoch seconds of last dismissal of same type
  cooldown_remaining_s: float,     # Seconds until suppression expires
  mode: Mode,                      # Current mode (affects privacy risk factor)
  attention_load: float,           # [0,1] current cognitive load estimate
  escalation_count: int            # Times this event was QUEUEd without ack
)
```

**U:** New event with `(urgency: float, content_type: str, risk_class: RiskClass, audience: list[str])`

**Y:**
- `ObservationRecord.type == "acknowledgment"` — user acknowledged
- `ObservationRecord.type == "dismissal"` — user explicitly dismissed
- `ObservationRecord.type == "silence"` — no response within timeout window
- `ObservationRecord.type == "escalation"` — user escalated severity (e.g. "this is urgent")

**W:**
- ASR confidence error (speaker identity uncertain)
- Noisy environment (presence detection unreliable)
- Missing identity (shared device, unrecognized voice)
- Stale `attention_load` estimate (no recent interaction)

**f(X, U, W):**
```
net_value(action) = urgency_value(U, X.mode)
                  - interruption_cost(X.attention_load, X.cooldown_remaining_s)
                  - privacy_risk(U.audience, X.mode, W.identity_confidence)
                  + predicted_ack_likelihood(X) × value_of_acknowledgment
                  - time_to_decay_penalty(action)

decision = argmax_{INTERRUPT, QUEUE, DIGEST, SILENT} net_value(action)
```

**Suppression state machine:**
```
NORMAL →[INTERRUPT fired]→ SUPPRESSED[cooldown_ms]
SUPPRESSED →[cooldown expires]→ NORMAL
SUPPRESSED →[CRITICAL risk_class]→ FORCE_INTERRUPT
NORMAL →[same event QUEUEd 3× without ack]→ ESCALATION_PENDING
ESCALATION_PENDING →[next event of same type]→ INTERRUPT
```

**Transition classification:**
- `NORMAL → SUPPRESSED`: deterministic (cooldown set at fire time)
- `SUPPRESSED → NORMAL`: deterministic (timer-based)
- `SUPPRESSED → FORCE_INTERRUPT`: deterministic (risk_class gate)
- `NORMAL → ESCALATION_PENDING`: stochastic (depends on ack likelihood estimate)

---

## Agent 3: Authorization Service

**X:** Stateless — no persistent state. All state is provided via `AuthzRequest.context`.

**U:** `AuthzRequest(subject, resource, action, context: AuthzContext)`

**Y:** None (stateless evaluator)

**W:**
- Stale `mode` in context (mode not re-confirmed in 5 min on shared device)
- Stale auth token (age > 60s on shared device)
- Stale authz result cache (age > 30s) — hard veto

**f(X, U, W):**
```
if W.authz_cache_stale:
    return AuthzResponse(allowed=False, reason="authz_result_stale")
if W.mode_stale:
    effective_context = downgrade_to_FAMILY(U.context)
return policy_function(U.subject, U.resource, U.action, effective_context)
```

**Transition classification:**
- Allow/deny: deterministic (policy function is deterministic given non-stale context)
- Mode downgrade on staleness: deterministic (hard rule)

---

## Agent 4: Continuity Engine (Open Loop Processor)

**X:**
```
(
  open_loops: list[OpenLoop],          # Active loops with decay state
  pending_commitments: list[Commitment],
  follow_up_queue: list[FollowUp]
)
```

**U:** 
- New commitment created by CRK step 8
- Closure event (user confirmed resolution, workflow completed)
- Time elapsed (decay update trigger)

**Y:**
- User acknowledgment of resurfaced loop
- Workflow completion signal from workflow-runtime
- Explicit user cancellation

**W:**
- User unavailability (no attention slot for resurfacing)
- Conflicting priorities (multiple loops competing for same attention slot)
- `owner_confidence` below threshold (uncertain who owns the loop)

**f(X, U, W):**
```
# Decay update (time elapsed)
for loop in X.open_loops:
    loop.freshness = decay(loop.freshness, loop.decay_function, elapsed_s)
    if loop.freshness < 0.05 and loop.age_hours > loop.max_age_hours:
        loop.status = ABANDONED

# Resurfacing check
candidates = [l for l in X.open_loops
              if l.priority_score × l.freshness > attention_threshold
              and l.last_surfaced_at + l.min_resurfacing_interval_s < now()]
resurface = pick_highest_priority(candidates, X.attention_load)
```

**Transition classification:**
- Decay update: deterministic (closed-form function of elapsed time)
- Resurfacing decision: stochastic (depends on attention_load estimate)
- Closure: deterministic (event-triggered)
- Abandonment: deterministic (threshold-based)

---

## Agent 5: Workflow Runtime (Temporal)

**X:** Serialized workflow state (persisted in Temporal server; survives restarts)

**U:** 
- `workflow.start(workflow_id, params)` — creates new durable instance
- `workflow.signal(workflow_id, signal_name, payload)` — sends signal
- `workflow.query(workflow_id, query_name)` — reads state without side effects
- Timer expiry (internal Temporal signal)

**Y:** 
- Activity completion results
- Timeout events
- External signals (approval granted, user cancelled)

**W:**
- Worker crash (handled by Temporal replay — not a true disturbance)
- External service timeout (activity retry handles)
- Signal delivery delay

**Key invariant:** Workflow activities may read operational state and call site-readonly MCP tools. They may **never** directly actuate hardware. Actuation is always via orchestrator job creation (step 7b). This is invariant I-WR-01.

**Transition classification:**
- Activity execution: stochastic (depends on external service availability)
- Timer firing: deterministic
- Signal handling: exogenous

---

## Disturbance Taxonomy

| Disturbance | Origin | Handling strategy |
|-------------|--------|-------------------|
| ASR confidence error | Voice pipeline | Confidence threshold check; elicitation if below 0.6 |
| Missing identity | Shared device | Downgrade to FAMILY mode (ADR-027) |
| Stale sensor | Environment | Flag `SENSOR_STALE`; block actuation on affected zone |
| Service unavailable | Network/process | Degrade gracefully; return stub with `degraded=true` flag |
| Noisy environment | Physical | Increase ASR confidence threshold requirement |
| Stale authz result | Cache expiry | Hard veto on any action; re-authorize required |
| Conflicting mode signals | Multiple surfaces | Precedence rule: EMERGENCY > SITE > WORK > FAMILY > PERSONAL |
| LLM hallucination | Model error | AI_ADVISORY origin never auto-approves HIGH-risk (invariant I-01) |

---

## Closed-Loop vs Open-Loop Actions

| Action type | Class | Example | Feedback path |
|-------------|-------|---------|---------------|
| Read/query | Open-loop | Memory retrieval, sensor query | None required |
| Advisory response | Open-loop | Assistant answer, recommendation | `ObservationRecord` captures user response |
| Durable workflow start | Closed-loop | Multi-day reminder | Workflow signals close the loop |
| Site control job | Closed-loop | Irrigation start | Orchestrator completion event |
| Alert delivery | Closed-loop | INTERRUPT | `ObservationRecord` captures ack/dismiss |
| Mode change | Closed-loop | PERSONAL → WORK | Mode confirmation required after identity re-auth |

---

## Verification Requirements

Every agent transition must have a corresponding test in `tests/calibration/` or `tests/integration/` that:
1. Sets up initial state **X**
2. Applies input **U** and disturbance **W**
3. Asserts the output **f(X,U,W)** matches the specified transition class
4. For stochastic transitions: asserts behavior is within specified distribution bounds
