# Field Truth and Shadow Mode

**Status:** Active  
**Version:** 1.0.0  
**Owner:** AI eval lead

---

## Overview

Field truth is the practice of measuring what Computer actually does in live usage, and systematically comparing that against what human operators would have preferred. Shadow mode is the technical mechanism: a parallel policy evaluation that runs silently alongside live decisions, logging divergences for review.

Together, field truth + shadow mode close the loop between policy design and real-world calibration.

---

## Shadow Evaluation Methodology

### What Shadow Mode Does

For every CRK decision (attention, routing, tool selection), the system optionally evaluates the same `ExecutionContext` against a "shadow" policy (either a proposed new policy or a baseline-frozen historical policy). The live decision is applied; the shadow decision is logged.

If they diverge, a `DivergenceRecord` is written to the evaluation queue.

### Divergence Types

| Type | What it captures | Review priority |
| --- | --- | --- |
| `attention` | Live chose INTERRUPT; shadow chose DIGEST (or vice versa) | High |
| `routing` | Live routed to voice; shadow would have routed to screen | Medium |
| `tool_selection` | Live selected tool A; shadow would have selected tool B | Medium |
| `confidence` | Live expressed high confidence; shadow expressed low | High (leading indicator) |
| `mode` | Live in WORK mode; shadow would trigger FAMILY mode | High |

### Divergence Review Queue

The divergence queue (`GET /eval/shadow/divergences`) surfaces all logged divergences.

**Review trigger:** Any single divergence with `confidence_delta > 0.20` warrants manual review before the next policy change.

**Batch review:** Weekly, during the drift digest ritual, all unreviewed divergences are triaged:
- Confirmed preference for live decision: dismiss divergence
- Shadow decision preferred: file `ExpectationDelta` and investigate policy parameter
- Ambiguous: flag for longer observation window

---

## Baseline Freeze Windows

When conducting a controlled A/B policy comparison, a baseline must be frozen:

1. **Freeze baseline:** `POST /eval/shadow/baseline/freeze` — pins the current policy version as the evaluation reference point
2. **Deploy candidate policy:** New policy parameters active for live decisions
3. **No other changes during window:** One-factor change discipline (see below)
4. **Evaluate window:** Minimum 72h; longer for low-frequency decision classes
5. **Compare results:** Live divergence rate vs baseline; check all 11 Trust KPIs

**POST /eval/shadow/baseline/freeze** endpoint: `services/eval-runner/eval_runner/main.py`

---

## One-Factor Change Discipline

No simultaneous policy changes during an evaluation window. This is a hard operational rule.

Allowed during a freeze window:
- Bug fixes to non-policy code paths
- Infrastructure changes that don't affect decision behavior

Not allowed during a freeze window:
- Attention weight changes
- Confidence threshold changes
- Mode transition rule changes
- New tool registrations that affect routing

Violation of one-factor discipline makes evaluation results unreliable. The freeze window must be extended and the baseline re-frozen after any disallowed change.

---

## Canary Policy Rollout

Before full deployment of a new policy, use canary mode:

1. Run shadow evaluation for 72h minimum (no canary yet — pure measurement)
2. If divergence rate < 10% and no high-confidence divergences: proceed to canary
3. **Canary phase:** 10% of decisions use new policy; 90% use baseline
4. Monitor Trust KPIs for 24h: if any KPI degrades, automatic rollback
5. If stable: increase to 50%, then 100%

**Automatic rollback triggers:**
- `spoken_regret_rate` increases by > 0.02 within 4h of canary
- `privacy_incident_count` > 0 at any point
- `interrupt_dismissal_rate` > 0.35 sustained for 2h

**GET /eval/shadow/canary/status** endpoint: `services/eval-runner/eval_runner/main.py`

---

## Shadow Mode Endpoints

All shadow mode endpoints are implemented in `services/eval-runner/eval_runner/main.py`:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/eval/shadow` | POST | Submit a ShadowComparison for logging |
| `/eval/shadow/divergences` | GET | List divergence log (filter by type, limit) |
| `/eval/shadow/baseline/freeze` | POST | Freeze current policy as A/B baseline |
| `/eval/shadow/canary/status` | GET | Canary rollout health and divergence counts |

---

## Field Truth Principles

1. **Trust signals over theory.** If users are saying "not now" at rising rates, that is more important than what the policy model predicts.
2. **Divergence is information, not failure.** A high shadow divergence rate means the policy is being challenged — investigate before dismissing.
3. **Silence is also signal.** The absence of spoken regret does not mean everything is correct — it may mean users have stopped correcting and started ignoring.
4. **Calibrate on human-preferred decisions.** `ExpectationDelta` records (from `computer expect`) are the ground truth for what operators actually wanted.

See also:
- `docs/safety/drift-remediation-policy.md`
- `docs/delivery/policy-publish-gate.md`
- `docs/architecture/trust-kpis-and-drift-model.md`
