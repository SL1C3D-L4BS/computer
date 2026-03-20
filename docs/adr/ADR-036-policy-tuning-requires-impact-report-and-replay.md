# ADR-036: Policy Tuning Requires PolicyImpactReport Before Replay, Replay Before Publish

**Status:** Accepted  
**Date:** 2026-03-19  
**Deciders:** Founder  

---

## Context

Attention and routing policy parameters (interruption weights, suppression cooldowns, confidence thresholds) are tunable at runtime via the Policy Tuning Console. Without gates, a well-intentioned but poorly validated parameter change can silently shift system behavior in ways that only manifest over days or weeks.

Past incidents where "just tweaking the threshold a bit" led to:
- Attention fatigue spike (dismissal rate 0.30 → 0.48 within 6h)
- Regret rate increase (spoken regret triggered more frequently)
- Silent regressions in routing accuracy that took 72h to detect

## Decision

**Three hard gates before any policy change can be published:**

1. **PolicyImpactReport required before replay begins.** The operator must declare: what is changing, what metrics are expected to shift, in which direction, and with what confidence. This prevents post-hoc rationalization of a bad change.

2. **Replay required before publish.** The proposed parameter must be replayed against the last N relevant historical traces (N ≥ 50 for interruption weights; N ≥ 100 for confidence thresholds). Divergence rate must be within rollback threshold.

3. **Approval-grade auth (passkey re-auth) required to publish.** A session token alone cannot authorize a policy publish. The operator must re-authenticate via passkey (approval track per ADR-034).

**Publish is blocked, not just warned.** The system does not allow publishing if any of the three gates are incomplete.

## Consequences

**Positive:**
- Policy changes have documented expected impact before deployment
- Divergence detected in replay before live users are affected
- Approval track ensures accountable, attributed policy changes

**Negative:**
- Slows down experimental iteration (acceptable cost; fast iteration on policy is a liability)
- Requires replay infrastructure to be operational (stubbed in V4; production in V5)

## Related

- `docs/delivery/policy-publish-gate.md`
- `docs/product/policy-tuning-console.md`
- `packages/runtime-contracts/models.py` — `PolicyImpactReport`, `ExpectationDelta`
