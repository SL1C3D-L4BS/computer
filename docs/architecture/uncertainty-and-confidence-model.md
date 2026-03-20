# Uncertainty and Confidence Model

**Status:** SPECIFIED  
**Authority:** runtime-kernel (threshold enforcement); all services (confidence production)  
**Depends on:** system-state-model.md, transition-and-control-model.md  
**ADR refs:** ADR-020 (authorization graph), ADR-027 (mode transitions), ADR-032 (shared-device rule)

---

## Design Principle

Computer operates under uncertainty at every decision layer. Uncertainty is **not a bug to be hidden** — it is a first-class input to every decision. Confidence must be:

1. **Typed** — different kinds of confidence are not interchangeable
2. **Propagated** — confidence compounds through the CRK steps
3. **Threshold-gated** — low confidence triggers clarification, abstention, or human approval
4. **Logged** — every `ConfidenceScore` written to audit trail for calibration

---

## Confidence Types

### IdentityConfidence

**Source:** voice-gateway (voice print match), auth-service (token validation), shared-device detector  
**Scale:** [0, 1]  
**Semantics:** 1.0 = cryptographically verified identity; 0.0 = completely unknown speaker  
**Decay:** 0.01 per minute after last voice interaction; 0.0 immediately on session end if shared device  
**Staleness:** expires after 60s on shared device without re-auth  

| Range | Interpretation | Implication |
|-------|---------------|-------------|
| [0.9, 1.0] | Verified (token + voice biometric) | PERSONAL mode permitted |
| [0.7, 0.9) | High confidence voice match | PERSONAL mode with monitoring |
| [0.5, 0.7) | Moderate confidence | FAMILY mode; no personal data |
| [0.3, 0.5) | Low confidence (shared device ambiguous) | FAMILY mode; limited actions |
| [0.0, 0.3) | Unknown speaker | GUEST mode; read-only |

---

### IntentConfidence

**Source:** NLU pipeline, ASR output score  
**Scale:** [0, 1]  
**Semantics:** 1.0 = unambiguous intent classification; 0.0 = completely ambiguous  
**Decay:** none (point-in-time measurement; computed fresh per request)  

| Range | Interpretation | Implication |
|-------|---------------|-------------|
| [0.8, 1.0] | Clear intent | Proceed |
| [0.6, 0.8) | Probably correct | Proceed with confirmation for HIGH-risk |
| [0.4, 0.6) | Ambiguous | Elicit clarification before proceeding |
| [0.0, 0.4) | Unintelligible | Request repeat; do not classify |

---

### ModeConfidence

**Source:** runtime-kernel step 3 (context-router)  
**Scale:** [0, 1]  
**Semantics:** certainty that the mode assigned to this request is correct  
**Decay:** 0.005 per minute on shared device without re-confirmation  

Computed from: `IdentityConfidence × mode_prior(surface, time_of_day) × recency_factor`

---

### MemoryConfidence

**Source:** memory-service (retrieval pipeline)  
**Scale:** [0, 1]  
**Semantics:** combined relevance score × source confidence × freshness of the retrieved memory  

```
MemoryConfidence = retrieval_relevance_score × source_confidence × freshness
```

| Range | Interpretation | Implication |
|-------|---------------|-------------|
| [0.7, 1.0] | Highly relevant, fresh | Use directly |
| [0.4, 0.7) | Possibly relevant | Flag as uncertain in response |
| [0.0, 0.4) | Low relevance or stale | Do not use; query user for update |

---

### EventSeverityConfidence

**Source:** digital-twin, Frigate, MQTT sensor pipeline  
**Scale:** [0, 1]  
**Semantics:** certainty that a sensor reading or detected event represents what it claims  
**Decay:** 0.001 per second for real-time readings; point-in-time for discrete events  

Cross-validation rule: if two independent sensors confirm the same event, confidence = min(c1, c2) + 0.1 × (1 - min(c1, c2)). Single sensor for CRITICAL events requires human confirmation.

---

### ToolRecommendationConfidence

**Source:** AI model (LLM), context-router  
**Scale:** [0, 1]  
**Semantics:** certainty that the recommended tool/action matches the intent and context  
**Decay:** none (point-in-time)  

This is the most variable confidence type. AI models are not calibrated out of the box. Calibration tests (Brier score) must validate that reported confidence correlates with actual accuracy.

---

### ActuationProposalConfidence

**Source:** orchestrator (when creating control jobs from workflow-runtime signals)  
**Scale:** [0, 1]  
**Semantics:** certainty that the proposed actuation is safe, appropriate, and intended  

This is a **composite** score:
```
ActuationProposalConfidence = min(
    IdentityConfidence,
    IntentConfidence,
    ModeConfidence,
    ToolRecommendationConfidence,
    EventSeverityConfidence_of_triggering_event  # if event-triggered
)
```

HC-03 applies: must be ≥ 0.70 for HIGH/CRITICAL risk. Must be ≥ 0.40 for any actuation.

---

## Confidence Propagation Rules

### Through CRK Steps

```
effective_confidence = propagate(confidence_scores: list[ConfidenceScore]) -> float
```

Three propagation modes (see `confidence-aggregation-rules.md` for full spec):

| Path type | Rule |
|-----------|------|
| HIGH/CRITICAL risk, safety-critical invariants | `hard_minimum = min(all scores)` |
| MEDIUM risk, advisory paths | `conservative = 0.7 × min + 0.3 × mean` |
| LOW risk, informational | `weighted_mean(scores, weights=recency)` |

The CRK step 6 (authz check) receives `effective_confidence` computed from all prior steps.

### Hard Veto Rules

These override any aggregation calculation and cannot be bypassed by objective weighting:

| Condition | Veto | Source |
|-----------|------|--------|
| Authz result age > 30s | `effective_confidence = 0.0`; action blocked | authz-service cache |
| Identity token age > 60s on shared device | `effective_confidence = 0.0` | voice-gateway / auth-service |
| Mode not confirmed in last 5min on shared device | Downgrade to FAMILY mode | runtime-kernel step 3 |
| ASR confidence < 0.35 | Request rejected; ask user to repeat | voice-gateway |
| Single sensor CRITICAL event, `EventSeverityConfidence < 0.6` | Require human confirmation | digital-twin |

---

## Abstention and Fallback Behavior

When `effective_confidence` falls below threshold, the system has three options. The correct one depends on `risk_class` and `origin`:

| Condition | Action | Rationale |
|-----------|--------|-----------|
| `HIGH/CRITICAL` + confidence < 0.70 | **Require human approval** | Cannot proceed autonomously |
| `MEDIUM` + confidence < 0.60 | **Elicit clarification** | User can resolve ambiguity cheaply |
| `LOW` + confidence < 0.40 | **Abstain with explanation** | Better to skip than guess |
| Any + confidence < 0.40 | **Reject** | Below minimum floor |
| `AI_ADVISORY origin` + `HIGH/CRITICAL` | **Always require human approval** | ADR-002; invariant I-01 |

Abstention messages must state what confidence type failed and what the user can provide to resolve it. "I'm not sure what you mean" is not acceptable. "I couldn't identify the speaker on this shared device — please say the wake word after logging in" is acceptable.

---

## Uncertainty Vector

For complex multi-step decisions, `UncertaintyVector` captures per-type confidence at once:

```python
@dataclass
class UncertaintyVector:
    identity:     ConfidenceScore   # Who is speaking/requesting
    intent:       ConfidenceScore   # What they want
    mode:         ConfidenceScore   # Operating context correctness
    memory:       ConfidenceScore   # Retrieved context reliability
    severity:     ConfidenceScore   # Event importance certainty
    tool_rec:     ConfidenceScore   # Recommended action correctness
    actuation:    ConfidenceScore   # Safe to actuate (if applicable)
```

The `UncertaintyVector` is attached to `ExecutionContext` when complexity warrants it (multi-step workflows, actuation proposals, MEDIUM+ risk).

---

## Calibration Requirements

Confidence scores are **only meaningful if calibrated**. A model reporting 0.8 confidence should be correct ~80% of the time. The following calibration checks are required:

| Confidence type | Calibration method | Target Brier score |
|----------------|-------------------|-------------------|
| IntentConfidence | Offline eval corpus (NLU fixtures) | < 0.15 |
| ToolRecommendationConfidence | Replay eval against labeled interactions | < 0.20 |
| predicted_ack_likelihood (attention) | ObservationRecord replay comparison | < 0.25 |
| EventSeverityConfidence | Sensor validation against ground truth | < 0.10 |

Calibration tests live in `tests/calibration/test_confidence_calibration.py`.

---

## Observability

Every `ConfidenceScore` emitted by any service must:
1. Be included in the `DecisionRationale` of the decision it informs
2. Be written to the structured audit log via `runtime-kernel` audit endpoint
3. Carry `computed_at` timestamp for staleness detection
4. Carry `source` field identifying which service/step produced it

Uncalibrated or unlogged confidence scores are treated as `confidence = 0.0` by the rubric check.
