# Cross-Domain Priority Model
**Status**: V5 Seed — Problem Statement Only. Do not implement until V4 is operationally stable.

---

## Problem Statement

`Computer` operates across four distinct control domains — **Personal**, **Family**, **Site Operations**, and **Safety** — each with its own trust model, attention budget, and intervention semantics. As of V4, these domains are separated by routing rules and trust tiers, but there is no formal model for **resolving cross-domain conflicts when a single decision simultaneously affects multiple domains**.

### Example Conflicts

1. A **voice alarm** for an emergency (Safety domain) fires while a **family approval** is in progress (Family domain). Which interrupts first?
2. A **site automation routine** (Site domain) triggers a robot path near children while a **personal workflow** is active for a family member (Personal domain). How does the system arbitrate?
3. A **personal memory access** request conflicts with a **family privacy boundary** — both resolve within the same trust tier but different domains.
4. A **founder mode** decision (Personal/Ops hybrid) overrides a previously committed Family reminder. How is the override logged and surfaced to the family member?

---

## Why This Requires a Formal Model

Ad-hoc priority logic leads to:
- **Invisible overrides**: Higher-priority domains silently cancel in-progress lower-priority flows.
- **Inconsistent interruption semantics**: Safety fires immediately; Family requires acknowledgment; Personal may be suppressed.
- **Unauditable conflicts**: No canonical record of which domain won a conflict and why.
- **Operator confusion**: "Why did the system not remind me?" — a Family reminder was preempted by a Site ops sweep.

---

## Candidate Model Framing (V5 to Explore)

### Domain Hierarchy (Proposed)

```
Safety > Site Critical > Family > Personal > Ops Advisory
```

The hierarchy is not a simple override list; it is a **partial order with conditional edges**:
- Safety preempts everything, but Safety actions still require acknowledgment within a bounded window.
- Site Critical preempts Personal, but not in-progress Family approval flows unless the `CriticalityScore` exceeds a configurable threshold.
- Family preempts Personal in shared-room contexts; not in private/solo contexts.
- Ops Advisory is advisory only and never preempts.

### Required Types (V5)

```python
@dataclass
class DomainConflict:
    conflict_id: str
    timestamp: str
    domains: list[str]                 # ["family", "safety"]
    competing_actions: list[str]       # action IDs
    resolution: str                    # which action won
    resolution_reason: str             # why
    preempted_actions: list[str]       # what was cancelled/deferred
    audit_payload: dict[str, Any]

@dataclass
class CrossDomainPriorityRule:
    id: str
    higher_domain: str
    lower_domain: str
    condition: str                     # When this preemption fires
    preemption_type: str               # "cancel" | "defer" | "parallel"
    acknowledgment_required: bool
    audit_required: bool
```

### Open Design Questions (for V5 investigation)

1. **Partial order vs. total order**: Should cross-domain priority be a total strict order, or can some pairs be context-dependent (e.g., Personal vs. Family depends on room presence)?
2. **Conflict visibility**: Should preempted actions surface to the affected domain's operator UI, or only to audit logs?
3. **Compensation patterns**: When a cross-domain preemption cancels a Family commitment, who is responsible for compensation — the Safety domain that triggered it, or the Orchestrator?
4. **Temporal priority decay**: Should a lower-priority action that has been waiting for N minutes gain priority?
5. **Multi-party acknowledgment**: If Safety preempts a Family approval, should the family member be notified and given a re-approval window after the emergency resolves?

---

## V5 Acceptance Criteria (Placeholder)

V5 implementation is complete when:
- [ ] `CrossDomainPriorityRule` registry is defined with ≥6 rules covering Safety→Family, Safety→Personal, Site→Personal, Family→Personal, and Ops→Family paths.
- [ ] Every conflict that resolves in production emits a `DomainConflict` record to the audit log.
- [ ] `computer trust report` includes `cross_domain_conflict_rate` as a KPI.
- [ ] `policy-tuning` console can adjust conditional edge thresholds with replay gate.
- [ ] At least one test in `tests/calibration/` validates that Safety preemption fires before Family under a simulated concurrent conflict.

---

## Relationship to V4

This model is **not implemented in V4**. V4 establishes:
- Trust tiers (`founder`, `family`, `site`) — prerequisite for domain typing.
- Attention plane with suppression/interrupt semantics — prerequisite for preemption logic.
- Drift monitors with owner assignment — prerequisite for per-domain conflict accountability.
- ReBAC authorization model — prerequisite for cross-domain permission checking.

V5 builds the **arbitration layer** on top of these V4 foundations.

---

*Do not implement until:*
1. *V4 is stable in production for ≥ 30 days.*
2. *At least 3 real cross-domain conflicts have been observed and logged.*
3. *The observed conflict patterns validate or refute the candidate model above.*
