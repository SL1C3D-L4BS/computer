# Experimental Design and Evaluation

**Status:** SPECIFIED  
**Authority:** eval-runner; reflection-engine (consumes results)  
**Depends on:** objective-functions.md, uncertainty-and-confidence-model.md  
**ADR refs:** ADR-031 (AI evaluation plane)

---

## Governing Principle

Nothing is shipped as "improved" without a measurement. Every V3 behavior change must state:
1. What hypothesis it tests
2. What metric it changes and in which direction
3. What the minimum detectable effect is
4. What sample size is sufficient
5. What would trigger a rollback

Without these, the reflection-engine learns false lessons and the system drifts toward unmeasured vibes.

---

## Eval Tiers

### Tier 1: Offline Evaluation

**When:** Before any code ships. Runs in CI.  
**Method:** Labeled fixture corpus, no live services  
**Tooling:** `eval-runner` POST `/eval/run`, `packages/eval-fixtures/`  
**Coverage:** Intent classification accuracy, confidence calibration, invariant pass/fail, routing correctness

Required for:
- Any change to the NLU pipeline
- Any change to attention decision weights
- Any change to confidence thresholds
- Any change to mcp-gateway policy

**Success gate:** All labeled fixtures produce expected `expected_decision` or within stated `tolerance`

---

### Tier 2: Replay Evaluation

**When:** After passing offline; before shadow deployment  
**Method:** Re-run recorded real interactions against the new code  
**Tooling:** `services/eval-runner/` replay mode with recorded `ObservationRecord` corpus  
**Coverage:** Behavioral regression — does new code produce the same or better decisions on historical traffic?

Required for:
- Any change to attention engine scoring
- Any change to CRK step ordering or logic
- Reflection-engine proposed policy adjustments

**Success gate:** Decision agreement rate ≥ 95% on historical corpus; regressions in safety-relevant categories = 0

---

### Tier 3: Shadow Evaluation (Live)

**When:** After passing replay; before A/B or canary deployment  
**Method:** New policy runs alongside old in shadow mode; outputs are logged but not delivered to user  
**Tooling:** `eval-runner` shadow mode; OTEL diff dashboards  
**Coverage:** Real traffic distribution, edge cases not in fixture corpus

**Baseline freeze requirement:** The old policy's outputs are captured at shadow-start. Any subsequent changes invalidate the shadow run. One shadow run = one policy variable change.

**Success gate:** Shadow policy meets objective targets ≥ old policy on soft objectives; hard constraints met 100%

---

### Tier 4: Red-Team Evaluation

**When:** Before any change that affects privacy, safety, or trust invariants  
**Method:** Adversarial prompt suite targeting known failure modes  
**Tooling:** `packages/eval-fixtures/` red_team category; manual adversarial additions  
**Coverage:** Privacy leakage, invariant bypass attempts, shared-device ambiguity exploitation, identity spoofing

Required for:
- Any change to authz-service policy
- Any change to identity/mode confidence thresholds
- Any change to memory scope enforcement
- Any new MCP tool registration

**Success gate:** All adversarial fixtures produce `expected_decision = REJECT` or `CLARIFY`; no fixture produces unintended data exposure

---

### Tier 5: Canary Policy Evaluation

**When:** Final validation before full rollout  
**Method:** New policy applied to a fraction (e.g. 10%) of real interactions; metrics compared  
**Tooling:** Runtime-kernel policy flag; OTEL metrics split by `policy_version` label  
**Coverage:** Production load distribution, unknown unknowns

**Minimum duration:** 48 hours continuous operation without rollback triggers  
**Rollback triggers:** Any hard constraint violation; any invariant failure in production; soft objective regression > 10% from baseline

---

## Required Artifacts Per V3 Behavior Change

Every new V3 behavior (continuity, attention upgrade, founder mode, reflection adjustments) must have a corresponding entry in `docs/delivery/eval-registry.md` with:

| Field | Description |
|-------|-------------|
| `behavior_id` | Unique ID (e.g. `V3-CONTINUITY-01`) |
| `hypothesis` | "We believe X will cause Y" |
| `primary_metric` | Single most important metric |
| `secondary_metrics` | Supporting metrics |
| `success_threshold` | Minimum acceptable value for primary metric |
| `rollback_threshold` | Value at which rollback is triggered |
| `sample_size_justification` | Why the chosen sample size is sufficient |
| `eval_tiers_required` | Which of T1–T5 are required |
| `baseline_frozen_at` | Timestamp when baseline was captured |
| `status` | `HYPOTHESIS` → `MEASURED` → `VALIDATED` → `PRODUCTION` |

---

## Causal Attribution Requirements

The reflection-engine is only as good as the causal attribution of changes. Without attribution, improvements look random and regressions are unexplained.

### One-Factor Rule

Each shadow or canary evaluation should change **exactly one policy variable**. If multiple variables change simultaneously, attribution is impossible.

Permitted exceptions: breaking changes that require simultaneous updates (e.g. schema migration). These must be documented as confounded evaluations with explicit uncertainty.

### Ablation Reports

For any behavior improvement claimed after a V3 phase, an ablation report must be filed in `docs/delivery/ablation-reports/`:

```
# Ablation Report: {behavior_id}

## Change
Describe the single variable changed.

## Baseline
{primary_metric} = {baseline_value} (captured {baseline_frozen_at})

## Result
{primary_metric} = {result_value} after {duration} of shadow/canary

## Components tested
- With component X: {metric_value}
- Without component X: {metric_value}
- Conclusion: component X accounts for {N}% of the improvement

## Confounds acknowledged
List any other changes that occurred during the measurement window.
```

### Counterfactual Replay

For attention and continuity improvements specifically, the replay tier must include a **counterfactual test**: run the same interaction corpus with the old policy and measure the counterfactual decision distribution. Delta = new - old.

---

## Calibration Metrics Reference

| Metric | Target | Measurement method |
|--------|--------|--------------------|
| Brier score (intent) | < 0.15 | Offline eval on labeled corpus |
| Brier score (attention ack) | < 0.25 | `ObservationRecord` replay comparison |
| Invariant pass rate | 100% | CI test_invariant_failure_injection.py |
| Routing precision | ≥ 0.90 | Labeled routing fixture corpus |
| Routing recall | ≥ 0.90 | Same corpus |
| False escalation rate | < 0.05 | Replay eval; INTERRUPT when QUEUE correct |
| Dismissal rate | < 0.15 | ObservationRecord from live shadow |
| Open loop closure rate | > accumulation rate | ComputerState audit trail |
| Privacy violation rate | 0.00 | Red-team eval; live monitoring |

---

## Confusion Matrix Categories for Assistant Routing

Every routing change must produce a confusion matrix with the following categories:

| Predicted \ Actual | INTERRUPT | QUEUE | DIGEST | SILENT |
|-------------------|-----------|-------|--------|--------|
| **INTERRUPT** | TP | FP_over | FP_over | FP_over |
| **QUEUE** | FN_under | TP | FP_minor | FP_minor |
| **DIGEST** | FN_under | FN_minor | TP | FP_minor |
| **SILENT** | FN_critical | FN_major | FN_minor | TP |

`FN_critical` (predicting SILENT when INTERRUPT was correct) is the most dangerous error class. Any regression in this cell triggers immediate rollback regardless of other metrics.

---

## Statistical Comparison Requirements

For A/B comparisons on live traffic:
- Minimum 200 observations per condition before drawing conclusions
- Use paired t-test for continuous metrics; chi-squared for categorical
- Report p-value and effect size (Cohen's d or Cramér's V)
- Report confidence intervals, not just point estimates
- Corrections for multiple comparisons (Bonferroni) when testing > 3 metrics simultaneously

For small-N attention calibration tests (< 200 interactions):
- Use bootstrap resampling (1000 iterations) for confidence intervals
- Report width of CI explicitly; conclusions require CI width < 0.1
