# Policy Publish Gate

**Status:** Active — Hard Invariant  
**Version:** 1.0.0  
**Enforced by:** `perfection_rubric.py` `v4_operational` category, `ops-web/policy-tuning`

---

## Hard Invariants

These three rules are non-negotiable. There is no override path that bypasses all three.

> **Rule 1:** No policy change may be published until it has been replayed against the last N relevant historical traces.

> **Rule 2:** Every policy change must declare a `PolicyImpactReport` **before** replay begins.

> **Rule 3:** Publish is blocked until: impact report filed, replay complete, divergence within threshold, passkey re-auth done.

Violation of any rule is a process failure, not a policy failure. It must be documented and the cause addressed before the next change.

---

## Gate Details

### Gate 1: PolicyImpactReport (before replay)

The operator must declare before replay what is expected to happen:

```python
PolicyImpactReport(
    parameter_changed="attention.interrupt_net_value_threshold",
    current_value=0.0,
    proposed_value=0.15,
    affected_metrics=["interrupt_dismissal_rate", "suggestion_acceptance_rate"],
    expected_direction={
        "interrupt_dismissal_rate": "decrease",
        "suggestion_acceptance_rate": "increase",
    },
    confidence=0.78,
    filed_by="founder",
    filed_at="2026-03-19T10:00:00Z",
)
```

All fields are required. `confidence` is the operator's prediction confidence (0–1) for the stated direction. This is not the model's confidence — it is the operator's epistemic state.

The impact report is immutable once filed. It cannot be edited after replay begins.

### Gate 2: Replay (before publish)

Minimum trace counts:
| Parameter class | Minimum N |
| --- | --- |
| Interruption weights | 50 |
| Confidence thresholds | 100 |
| Routing parameters | 30 |
| Founder density | 20 |

Divergence threshold: publish is blocked if divergence rate > 15% for interruption weights or > 10% for confidence thresholds.

Traces selected: the last N traces in the relevant decision class (by mode and decision type). Traces from before the last baseline freeze are excluded.

### Gate 3: Passkey Re-auth (approval track)

The operator must complete a WebAuthn passkey ceremony at publish time. The session token alone is insufficient. The passkey ceremony is action-bound: the approval token encodes the `policy_version` and `parameter_changed` fields from the impact report.

This ensures:
- The operator who filed the impact report is the operator who publishes
- The approval is specific to this change (not a blanket "approve everything")
- The action is attributable and auditable

---

## Divergence Threshold Policy

If divergence rate exceeds rollback threshold:
1. Publish is blocked
2. The operator must review high-divergence traces individually
3. Two paths:
   - Revise the parameter and replay again (new impact report not required if parameter class unchanged)
   - Accept divergence and document why (requires escalation to second approver)

---

## ExpectationDelta Integration

`ExpectationDelta` records (captured via `computer expect`) feed into the replay evaluation. If a human correction exists for a trace type similar to the proposed change:
- The correction is surfaced in the replay viewer
- The operator must acknowledge it before proceeding

This closes the feedback loop: corrections from operators in the field inform policy change decisions.

---

## Audit Record Format

Every publish event creates an immutable audit record:

```python
{
  "policy_change_id": "pc-abc123",
  "parameter_changed": "attention.interrupt_net_value_threshold",
  "old_value": 0.0,
  "new_value": 0.15,
  "impact_report": PolicyImpactReport(...),
  "replay_summary": {
    "trace_count": 52,
    "divergence_rate": 0.08,
    "affected_kpis": {...}
  },
  "approval_token_id": "tok-xyz789",
  "approved_by": "founder",
  "published_at": "2026-03-19T10:45:00Z",
  "policy_version_before": "1.4.2",
  "policy_version_after": "1.5.0",
}
```

---

## Emergency Rollback Path

If a published change causes an immediate quality incident:
1. Notify AI eval lead (drift-remediation-policy.md escalation path)
2. Identify the previous known-good policy version from `history/page.tsx`
3. File an expedited `PolicyImpactReport` with `confidence=1.0` and `expected_direction=rollback`
4. Replay is waived for emergency rollback if `privacy_incident_count > 0`
5. Passkey re-auth still required
6. Document the incident in the drift log within 24h

See also: `docs/safety/drift-remediation-policy.md`
