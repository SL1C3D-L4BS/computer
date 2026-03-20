# Objective Functions

**Status:** SPECIFIED  
**Authority:** runtime-kernel (enforces); attention-engine, authz-service (consume)  
**Depends on:** system-state-model.md, hard-constraints-vs-soft-objectives.md (when written)  
**ADR refs:** ADR-002 (AI advisory boundary), ADR-021 (attention), ADR-027 (mode transitions)

---

## Critical Design Rule

Objective functions are **lexicographically structured**. Hard constraints define the feasible region. Soft objectives are only optimized *inside* that region. A weighted sum that numerically trades safety for convenience is **not permitted**.

```
DECISION = argmax_{action ∈ FEASIBLE(hard_constraints)} soft_objective(action, context)
```

If the feasible set is empty (all actions violate at least one hard constraint), the system must **abstain**, **clarify**, or **reject** — never satisfy a hard constraint partially.

---

## Hard Constraints (Infeasibility Boundaries)

These constraints are **never relaxed by any objective weighting**. Violation makes an action infeasible regardless of soft objective values.

| ID | Constraint | Enforcement |
|----|-----------|-------------|
| HC-01 | `privacy_preservation = true` — any scope violation makes action infeasible | authz-service; invariant I-02, I-03 |
| HC-02 | `unsafe_actuation_risk = 0` for AI_ADVISORY origin | runtime-kernel step 7; invariant I-01 |
| HC-03 | `effective_confidence ≥ 0.70` for HIGH/CRITICAL risk_class | runtime-kernel step 6 check; invariant I-06 |
| HC-04 | `effective_confidence ≥ 0.40` for any action | runtime-kernel step 6 check; invariant I-06 |
| HC-05 | `authz_result.allowed = true` | runtime-kernel step 6; invariant I-05 |
| HC-06 | `step_7a_exclusive_of_7b` per request trace | runtime-kernel step 7; invariant I-04 |
| HC-07 | `authz_result_age_s < 30` — stale authz blocks any action | authz-service cache; confidence-aggregation-rules.md |
| HC-08 | `mode_change_reason != null` when mode differs from prior value | runtime-kernel step 3; invariant I-07 |

---

## Soft Objectives by Domain

### Domain 1: Assistant Utility

**Optimization target:** maximize expected utility to the user per interaction

#### Maximize

```python
relevance(response, intent)          # [0,1] Semantic match between response and intent
timeliness(response, urgency)        # [0,1] 1.0 = delivered at optimal time; decays with latency
completion_rate(session)             # [0,1] Fraction of requests fully resolved in session
trust_retention(user, window_30d)   # [0,1] Net trust signal: acks, positive corrections, escalations
privacy_preservation(scope, mode)   # Binary HC-01; listed here for completeness
```

#### Minimize

```python
interruption_cost(event, context)    # [0,1] = attention_load × (1 - urgency_value)
false_escalation_rate(window)        # [0,1] INTERRUPT when QUEUE was correct
repeated_prompt_count(loop_id)       # Integer; target 0 for resolved loops
cognitive_load_imposed(session)      # [0,1] Measured by dismissal_rate × (1/response_latency_ratio)
```

#### Per-mode weights

| Objective term | PERSONAL | FAMILY | WORK | SITE | EMERGENCY |
|----------------|----------|--------|------|------|-----------|
| `relevance` | 0.30 | 0.25 | 0.35 | 0.15 | 0.10 |
| `timeliness` | 0.20 | 0.20 | 0.25 | 0.30 | 0.50 |
| `completion_rate` | 0.20 | 0.20 | 0.20 | 0.20 | 0.10 |
| `trust_retention` | 0.15 | 0.20 | 0.10 | 0.10 | 0.05 |
| `interruption_cost` | -0.15 | -0.15 | -0.10 | -0.25 | -0.25 |

> In EMERGENCY mode, `timeliness` dominates. All soft objectives that would delay a CRITICAL alert are overridden.

---

### Domain 2: Site Operations

**Optimization target:** maximize safe job throughput and resource efficiency

#### Maximize

```python
safe_job_completion_rate(window)     # [0,1] Jobs completed without incident
energy_efficiency_score(period)      # [0,1] Normalized energy per output unit
crop_health_score(current)           # [0,1] Aggregate sensor-derived health
incident_detection_quality(window)   # [0,1] True positive rate on safety events
```

#### Minimize

```python
unsafe_actuation_risk               # HC-02; listed here for completeness; weight = ∞
false_positive_rate(detections)     # [0,1] False alarms per total alerts
operator_burden(window)             # [0,1] Manual interventions / total jobs
equipment_wear_rate(assets)         # [0,1] Normalized wear vs baseline
latency_to_critical_response(ms)    # Integer; target < 2000ms for CRITICAL events
```

#### Per-mode weights

| Objective term | SITE | EMERGENCY |
|----------------|------|-----------|
| `safe_job_completion_rate` | 0.30 | 0.10 |
| `energy_efficiency_score` | 0.20 | 0.00 |
| `crop_health_score` | 0.20 | 0.00 |
| `incident_detection_quality` | 0.15 | 0.60 |
| `false_positive_rate` | -0.10 | -0.20 |
| `operator_burden` | -0.05 | -0.10 |

> In EMERGENCY mode, `incident_detection_quality` and zero false negatives dominate.

---

### Domain 3: Attention Delivery

**Optimization target:** maximize information value delivered while minimizing cognitive cost

#### Attention utility function (per event)

```
net_value(action, event, context) =
    urgency_value(event.urgency, context.mode) × mode_urgency_weight[context.mode]
  - interruption_cost(context.attention_load, context.cooldown_remaining_s)
  - privacy_risk(event.audience, context.mode, context.identity_confidence)
  + predicted_ack_likelihood(context) × value_of_acknowledgment(event.urgency)
  - time_to_decay_penalty(action, event.urgency_decay_rate)

decision = argmax_{INTERRUPT, QUEUE, DIGEST, SILENT} net_value(action, event, context)
```

All terms normalized to [0,1]. See `measurement-and-scaling-model.md` for normalization rules.

---

### Domain 4: Founder Decision Support

**Optimization target:** maximize decision throughput; minimize unresolved decision load

#### Maximize

```python
decisions_resolved_per_session       # Integer; target > 5 per briefing
backlog_burn_down_rate               # Float; target > 1.0 (resolving faster than accumulating)
decision_context_quality(register)  # [0,1] Quality of context attached to each decision
```

#### Minimize

```python
unresolved_decision_load             # Integer; trigger truncation threshold at 20
context_switch_cost(session)         # [0,1] Session interruptions per decisions resolved
mean_decision_age_hours              # Float; target < 48h for action-required tier
opportunity_cost_of_delay(decision)  # [0,1] Time-sensitive decisions past deadline
```

---

## Composite Utility for CRK Step 9 (Attention Gate)

At step 9, the CRK evaluates whether to deliver the response and how. The soft objective is computed within the feasible region (all HC passed):

```python
def compute_attention_utility(event, ctx, attention_memory) -> AttentionCost:
    urgency = scale_urgency(event.urgency, ctx.mode)        # [0,1]
    cost    = scale_cost(ctx.attention_load,                # [0,1]
                          attention_memory.cooldown_remaining_s)
    privacy = scale_privacy(event.audience, ctx.mode,      # [0,1]
                             ctx.identity_confidence)
    ack_p   = predict_ack_likelihood(ctx, attention_memory) # [0,1]
    decay_p = decay_penalty(event.urgency_decay_rate,       # [0,1]
                             action.delay_ms)
    net_val = urgency - cost - privacy + ack_p * ack_value - decay_p
    return AttentionCost(
        interruption_cost=cost,
        urgency_value=urgency,
        privacy_risk=privacy,
        predicted_ack_likelihood=ack_p,
        net_value=net_val
    )
```

---

## Objective Weight Versioning

Objective weights are versioned and tracked. Changes to weights are:
1. Proposed by `reflection-engine` as `CandidatePolicyAdjustment` with `adjustment_type = "objective_weight"`
2. Reviewed and approved by operator
3. Recorded with version bump in `meta_state.active_policy_version`
4. Shadow-tested for minimum 48h before promotion

Changes to **hard constraints** (HC-01 through HC-08) require ADR approval. They are not adjustable at runtime.
