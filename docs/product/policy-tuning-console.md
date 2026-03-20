# Policy Tuning Console

**Status:** Active  
**Version:** 1.0.0  
**Owner:** Founder / Attention-engine owner  
**Location:** `apps/ops-web/src/app/policy-tuning/`

---

## Overview

The Policy Tuning Console provides a safe interface for adjusting policy parameters that govern attention, routing, and decision behavior. Every change must be backed by a `PolicyImpactReport`, replayed against historical traces, and approved via passkey re-auth (approval track).

**This is not a settings panel.** Every parameter change is a hypothesis about system behavior. The console enforces the scientific discipline that hypothesis requires.

---

## Tunable Parameters

| Parameter | Domain | Current default | Effect |
| --- | --- | --- | --- |
| `attention.interrupt_net_value_threshold` | Attention | 0.0 | Minimum net_value required to trigger INTERRUPT |
| `attention.suppression_cooldown_s` | Attention | 300 | Cooldown after suppression before re-interrupt |
| `attention.urgency_decay_rate` | Attention | 0.1 | How fast urgency decays over time |
| `confidence.min_decision_threshold` | Confidence | 0.65 | Minimum confidence before abstaining |
| `confidence.abstention_floor` | Confidence | 0.40 | Below this: always abstain and ask |
| `loops.max_age_days` | Memory | 90 | Maximum loop age before forced abandonment |
| `loops.freshness_abandonment_threshold` | Memory | 0.05 | Freshness below this: abandon candidate |
| `loops.decay_rate` | Memory | 0.03 | Exponential decay rate for loop freshness |
| `founder.briefing_density` | Founder | "normal" | "sparse" / "normal" / "dense" |
| `founder.privacy_penalty_weight` | Privacy | 1.5 | Weight on privacy violations in attention cost |
| `routing.voice_length_budget_personal` | Voice | 2 | Max sentences in PERSONAL mode |
| `routing.voice_length_budget_family` | Voice | 3 | Max sentences in FAMILY mode |

---

## What-If Simulation

Before publishing any parameter change, the console requires replay:

1. Select parameter and proposed new value
2. File `PolicyImpactReport` (required before replay can begin)
3. Console selects N traces from the last 30 days relevant to the parameter class
4. Replay the N traces with the proposed value active
5. Compare attention decisions, routing decisions, and tool selections
6. Compute divergence rate and KPI delta predictions
7. If divergence rate within threshold and no KPI regressions: enable publish button

The replay viewer (`simulate/page.tsx`) shows each trace side-by-side: original decision vs proposed decision.

---

## Approval-Gated Publish (Hard Invariant)

**Publish is blocked until all three gates are complete.** This is not advisory.

| Gate | Requirement |
| --- | --- |
| Impact report | `PolicyImpactReport` filed with all fields populated |
| Replay | Minimum N traces replayed; divergence within threshold |
| Auth | Passkey re-auth (approval track) completed |

The publish button is disabled in the UI until all three gates are green. There is no override path that bypasses all three.

Minimum N traces per class:
- Interruption weights: N ≥ 50
- Confidence thresholds: N ≥ 100
- Routing parameters: N ≥ 30
- Founder density: N ≥ 20

---

## Audit Trail

Every policy change is logged with:
- Operator identity (from passkey credential)
- `PolicyImpactReport` (attached to the change record)
- Replay summary (divergence rate, affected traces, KPI deltas)
- Timestamp and policy version before/after

The history page (`history/page.tsx`) shows every change with the impact report attached. Policy changes are never silent.

---

## Console Pages

### `page.tsx` — Parameter Table
- Shows all tunable parameters with current values
- Edit control for each parameter (inline)
- Status indicator: which parameters have pending `PolicyImpactReport`
- "File Impact Report" button → opens impact report form

### `simulate/page.tsx` — Replay Viewer
- Shows parameter being tested, proposed value, replay progress
- Trace list: each trace with original decision and proposed decision
- Divergence rate summary
- Publish button (disabled until all gates complete)
- "Confirm publish" requires passkey re-auth before proceeding

### `history/page.tsx` — Policy Change Audit Log
- Chronological list of all policy changes
- Each entry: parameter, old value, new value, filed_by, filed_at
- Expandable `PolicyImpactReport` for each entry
- Replay summary expandable (divergence rate, trace count)

---

## Policy Rollback

Every published policy change creates a versioned checkpoint. To roll back:
1. Navigate to `history/page.tsx`
2. Find the previous version
3. Use "Restore this version" — same three-gate process applies (impact report + replay + auth)

Rollback is not instant — it requires the same rigor as a forward change. If an emergency rollback is needed (e.g., privacy incident), the drift remediation policy defines an accelerated path with explicit escalation.

See also:
- `docs/delivery/policy-publish-gate.md`
- `docs/delivery/field-truth-and-shadow-mode.md`
- `packages/runtime-contracts/models.py` — `PolicyImpactReport`, `ExpectationDelta`
