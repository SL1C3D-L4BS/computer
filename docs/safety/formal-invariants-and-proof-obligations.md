# Formal Invariants and Proof Obligations

**Status:** SPECIFIED  
**Authority:** runtime-kernel (enforcement); CI (regression gate)  
**Depends on:** uncertainty-and-confidence-model.md, objective-functions.md  
**Proof obligation test:** `tests/calibration/test_invariant_failure_injection.py`  
**ADR refs:** ADR-002 (AI advisory), ADR-004 (mode isolation), ADR-029 (traceability)

---

## Principle

Named invariants are **proof obligations**, not guidelines. Each invariant has:
- A precise statement
- A named enforcement location
- A proof mechanism (unit test, integration test, static analysis, or runtime assertion)
- A test reference that exercises the invariant by deliberate violation
- A rubric check that fails CI if the enforcement is removed

Invariants are numbered and stable. Adding a new invariant increments the count. Removing an invariant requires an ADR.

---

## Invariant Catalog

### I-01: AI Advisory Never Auto-Actuates

**Statement:** A request with `origin = AI_ADVISORY` must never result in a `7b_control_job` being created or an actuation being executed without an intermediate human approval step.

**Enforcement location:** `runtime-kernel/loop.py` step 7b gate; `orchestrator` job approval gate  
**Proof mechanism:** Integration test — submit AI_ADVISORY request with HIGH-risk intent; assert no job created without approval record  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I01_ai_advisory_no_auto_actuate`  
**Rubric check:** `RUNTIME_V2_CHECKS: "AI_ADVISORY never creates control job without approval"`

---

### I-02: Personal Memory Privacy in FAMILY Mode

**Statement:** Memory entries with `scope = PERSONAL` must never be returned in a request where `mode = FAMILY`, unless an explicit `share_relation` record exists between the requesting user and the memory owner.

**Enforcement location:** `memory-service` retrieval filter; `authz-service` policy function  
**Proof mechanism:** Unit test — query personal memory with FAMILY mode context; assert empty result  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I02_personal_memory_family_mode_isolation`  
**Rubric check:** `SECURITY_CHECKS: "personal memory isolated in FAMILY mode"`

---

### I-03: Emergency Mode Does Not Expand Memory Access

**Statement:** Activating `mode = EMERGENCY` must not grant access to `scope = PERSONAL` or `scope = WORK` memory beyond what the user's identity tier already permits.

**Enforcement location:** `authz-service` policy function; mode transition rules (ADR-027)  
**Proof mechanism:** Integration test — trigger EMERGENCY mode; assert memory scope unchanged  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I03_emergency_no_memory_expansion`  
**Rubric check:** `SECURITY_CHECKS: "EMERGENCY mode does not increase memory scope"`

---

### I-04: Step 7a and 7b Are Mutually Exclusive

**Statement:** For a single request trace identified by `trace_id`, exactly one of (7a tool invocation via mcp-gateway) OR (7b control job binding via orchestrator) may occur. Never both.

**Enforcement location:** `runtime-kernel/loop.py` step 7 gate  
**Proof mechanism:** Unit test — attempt to invoke both 7a and 7b in single loop pass; assert runtime error  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I04_7a_7b_mutually_exclusive`  
**Rubric check:** `RUNTIME_V2_CHECKS: "step 7a and 7b are mutually exclusive"`

---

### I-05: No Actuation with Stale or Unavailable Authz

**Statement:** Any request that would result in hardware actuation (step 7b) must have a valid, non-stale `AuthzResponse.allowed = true`. If authz-service is unavailable or the cached result is older than 30 seconds, the action is blocked.

**Enforcement location:** `runtime-kernel/loop.py` step 6; `orchestrator` job acceptance gate  
**Proof mechanism:** Integration test — disable authz-service; submit actuation request; assert rejection with `I-05` reason  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I05_stale_authz_blocks_actuation`  
**Rubric check:** `SECURITY_CHECKS: "actuation blocked without valid authz"`

---

### I-06: Confidence Threshold Gates High-Risk Actions

**Statement:** No HIGH or CRITICAL risk_class action may proceed with `effective_confidence < 0.70`. No action of any risk_class may proceed with `effective_confidence < 0.40`.

**Enforcement location:** `runtime-kernel/loop.py` step 6 (confidence gate)  
**Proof mechanism:** Unit test — submit HIGH-risk request with low-confidence context; assert rejection with `I-06` reason and `InvariantCheckResult` in response  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I06_confidence_threshold`  
**Rubric check:** `RUNTIME_V2_CHECKS: "confidence threshold gates high-risk actions"`

---

### I-07: Mode Change Requires Reason

**Statement:** Any `ExecutionContext` where `mode` differs from the previously sticky mode for `{user_id}:{surface}` must have a non-null, non-empty `mode_change_reason` field. A mode change without reason is an audit gap.

**Enforcement location:** `runtime-kernel/loop.py` step 3 (context enrichment)  
**Proof mechanism:** Unit test — trigger mode change; assert `mode_change_reason != null`; assert absent reason raises validation error  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I07_mode_change_requires_reason`  
**Rubric check:** `RUNTIME_V2_CHECKS: "mode change always carries reason"`

---

### I-08: trace_id Continuity

**Statement:** `ResponseEnvelope.trace_id` must always equal `InputEnvelope.trace_id` for the same request. No step may generate a new trace_id for an existing request.

**Enforcement location:** `runtime-kernel/loop.py` step 10 assertion  
**Proof mechanism:** Unit test — submit request; assert `response.trace_id == input.trace_id` across all 10 steps  
**Test ref:** `tests/crk/test_crk_loop.py::test_trace_id_continuity` (pre-existing)  
**Rubric check:** `EXECUTION_LOOP_CHECKS: "trace_id continuity"`

---

### I-09: Open Loops Decay to ABANDONED Before Max Age

**Statement:** An `OpenLoop` in status `ACTIVE` must never have `age_hours > max_age_hours` AND `freshness < 0.05` simultaneously. The decay processor must transition it to `ABANDONED` before that combination occurs.

**Enforcement location:** `services/runtime-kernel/` continuity processor  
**Proof mechanism:** Unit test — create loop with very short max_age; advance time; assert status transitions to ABANDONED  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I09_loop_decay_to_abandoned`  
**Rubric check:** `V3_CHECKS: "open loops decay to ABANDONED"`

---

### I-10: Reflection Engine Proposals Require Operator Approval

**Statement:** A `CandidatePolicyAdjustment` emitted by `reflection-engine` must never be applied to any service configuration or policy weight without an explicit `operator_approved = true` flag and an approval record in the audit log.

**Enforcement location:** `services/reflection-engine/` apply gate; operator approval API  
**Proof mechanism:** Integration test — emit adjustment proposal; attempt auto-apply; assert blocked with `I-10` reason  
**Test ref:** `tests/calibration/test_invariant_failure_injection.py::test_I10_no_auto_policy_apply`  
**Rubric check:** `V3_CHECKS: "reflection engine proposals require operator approval"`

---

## Proof Mechanism Reference

| Mechanism | When to use | Provides |
|-----------|-------------|----------|
| Unit test | Single-service logic, deterministic transitions | Fast; always in CI |
| Integration test | Cross-service invariants, fault injection | Slower; in integration CI lane |
| Static analysis | Code patterns (e.g. no `drone.arm` in mcp registry) | Structural; in pre-commit |
| Runtime assertion | Invariants that can only be checked at runtime | Defense-in-depth; not a primary gate |
| Rubric check | Artifact presence and structural correctness | Catches doc/code divergence |

---

## Violation Handling

When an invariant check fails at runtime, the system must:
1. Return an `InvariantCheckResult` with `passed=False` and the invariant ID
2. Log the violation as a structured audit event with full `ExecutionContext`
3. Reject the action (never silently degrade)
4. Increment the `invariant_violation_count` metric for the specific invariant ID

Invariant violations in CI fail the build immediately. They are not warnings.

---

## Adding New Invariants

1. Add a row to this document with a new I-N id
2. Add enforcement location and proof mechanism
3. Add a test in `tests/calibration/test_invariant_failure_injection.py`
4. Add a rubric check to `scripts/perfection_rubric.py`
5. Update `InvariantCheckResult` enum if needed

Invariants may not be removed without an ADR explaining why the constraint no longer applies.
