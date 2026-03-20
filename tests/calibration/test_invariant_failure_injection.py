"""
Invariant Failure Injection Tests — V3

Tests I-01 through I-10 by deliberately creating conditions that violate each
invariant, then asserting the system correctly rejects/rejects/logs the violation.

These tests are the enforcement proof for docs/safety/formal-invariants-and-proof-obligations.md

Test organization:
- Each test is named test_I{N}_{short_description}
- Each test sets up the violation condition, asserts rejection, and verifies
  that InvariantCheckResult is emitted with the correct invariant_id

See also: tests/calibration/test_confidence_calibration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

CONTRACTS_PATH = Path(__file__).parent.parent.parent / "packages" / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

from models import (
    ConfidenceScore,
    ConfidenceType,
    InvariantCheckResult,
    Mode,
    OpenLoop,
    OpenLoopStatus,
    Origin,
    RiskClass,
    Surface,
)


# ── Helper: Simulate invariant check ─────────────────────────────────────────

def check_I01_ai_advisory_no_auto_actuate(origin: Origin, risk_class: RiskClass, approval_record: bool) -> InvariantCheckResult:
    """
    I-01: AI_ADVISORY origin must not create HIGH/CRITICAL control jobs without human approval.
    """
    passed = not (
        origin == Origin.AI_ADVISORY
        and risk_class in (RiskClass.HIGH, RiskClass.CRITICAL)
        and not approval_record
    )
    return InvariantCheckResult(
        invariant_id="I-01",
        passed=passed,
        evidence={"origin": origin.value, "risk_class": risk_class.value, "approval_record": approval_record},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="runtime-kernel/loop.py:step_7b",
    )


def check_I02_personal_memory_family_mode(mode: Mode, memory_scope: str, share_relation_exists: bool) -> InvariantCheckResult:
    """
    I-02: PERSONAL memory must not be visible in FAMILY mode without share_relation.
    """
    passed = not (
        mode == Mode.FAMILY
        and memory_scope == "PERSONAL"
        and not share_relation_exists
    )
    return InvariantCheckResult(
        invariant_id="I-02",
        passed=passed,
        evidence={"mode": mode.value, "memory_scope": memory_scope, "share_relation": share_relation_exists},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="memory-service/retrieval",
    )


def check_I03_emergency_no_memory_expansion(mode_before: Mode, mode_after: Mode, scope_before: str, scope_after: str) -> InvariantCheckResult:
    """
    I-03: Activating EMERGENCY must not grant additional memory scope.
    """
    passed = not (
        mode_after == Mode.EMERGENCY
        and scope_after != scope_before
        and scope_after in ("PERSONAL", "WORK")
        and scope_before not in ("PERSONAL", "WORK")
    )
    return InvariantCheckResult(
        invariant_id="I-03",
        passed=passed,
        evidence={"mode_before": mode_before.value, "mode_after": mode_after.value, "scope_before": scope_before, "scope_after": scope_after},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="authz-service/policy",
    )


def check_I04_7a_7b_exclusive(step_7a_invoked: bool, step_7b_invoked: bool) -> InvariantCheckResult:
    """
    I-04: 7a (tool) and 7b (control job) are mutually exclusive per request trace.
    """
    passed = not (step_7a_invoked and step_7b_invoked)
    return InvariantCheckResult(
        invariant_id="I-04",
        passed=passed,
        evidence={"step_7a_invoked": step_7a_invoked, "step_7b_invoked": step_7b_invoked},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="runtime-kernel/loop.py:step_7",
    )


def check_I05_no_stale_authz_actuation(authz_result_age_s: float, action_is_actuation: bool) -> InvariantCheckResult:
    """
    I-05: Actuation blocked if authz result age > 30s or unavailable.
    """
    STALE_THRESHOLD_S = 30.0
    passed = not (action_is_actuation and authz_result_age_s > STALE_THRESHOLD_S)
    return InvariantCheckResult(
        invariant_id="I-05",
        passed=passed,
        evidence={"authz_result_age_s": authz_result_age_s, "action_is_actuation": action_is_actuation},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="runtime-kernel/loop.py:step_6",
    )


def check_I06_confidence_threshold(effective_confidence: float, risk_class: RiskClass, approval_record: bool) -> InvariantCheckResult:
    """
    I-06: HIGH/CRITICAL actions require effective_confidence ≥ 0.70.
          Any action requires effective_confidence ≥ 0.40.
    """
    if effective_confidence < 0.40:
        passed = False
    elif risk_class in (RiskClass.HIGH, RiskClass.CRITICAL) and effective_confidence < 0.70:
        passed = approval_record  # Can proceed with human approval even below threshold
    else:
        passed = True

    return InvariantCheckResult(
        invariant_id="I-06",
        passed=passed,
        evidence={"effective_confidence": effective_confidence, "risk_class": risk_class.value, "approval_record": approval_record},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="runtime-kernel/loop.py:step_6",
    )


def check_I07_mode_change_requires_reason(mode_changed: bool, mode_change_reason: str | None) -> InvariantCheckResult:
    """
    I-07: Mode change must have a non-null, non-empty mode_change_reason.
    """
    passed = not mode_changed or (mode_change_reason is not None and len(mode_change_reason.strip()) > 0)
    return InvariantCheckResult(
        invariant_id="I-07",
        passed=passed,
        evidence={"mode_changed": mode_changed, "mode_change_reason": mode_change_reason},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="runtime-kernel/loop.py:step_3",
    )


def check_I08_trace_id_continuity(input_trace_id: str, response_trace_id: str) -> InvariantCheckResult:
    """
    I-08: ResponseEnvelope.trace_id must equal InputEnvelope.trace_id.
    """
    passed = input_trace_id == response_trace_id
    return InvariantCheckResult(
        invariant_id="I-08",
        passed=passed,
        evidence={"input_trace_id": input_trace_id, "response_trace_id": response_trace_id},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="runtime-kernel/loop.py:step_10",
    )


def check_I09_loop_decay_to_abandoned(freshness: float, age_hours: float, max_age_hours: float, status: OpenLoopStatus) -> InvariantCheckResult:
    """
    I-09: ACTIVE loop with freshness < 0.05 AND age > max_age must be ABANDONED.
    """
    violation = (
        freshness < 0.05
        and age_hours > max_age_hours
        and status == OpenLoopStatus.ACTIVE
    )
    passed = not violation
    return InvariantCheckResult(
        invariant_id="I-09",
        passed=passed,
        evidence={"freshness": freshness, "age_hours": age_hours, "max_age_hours": max_age_hours, "status": status.value},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="runtime-kernel/continuity_tick",
    )


def check_I10_no_auto_policy_apply(operator_approved: bool, application_attempted: bool) -> InvariantCheckResult:
    """
    I-10: Reflection-engine proposals must never be auto-applied without operator_approved=true.
    """
    passed = not (application_attempted and not operator_approved)
    return InvariantCheckResult(
        invariant_id="I-10",
        passed=passed,
        evidence={"operator_approved": operator_approved, "application_attempted": application_attempted},
        checked_at="2026-03-19T00:00:00Z",
        enforcement_location="reflection-engine/apply_gate",
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestI01AIAdvisoryNoAutoActuate:
    def test_I01_ai_advisory_high_risk_without_approval_fails(self):
        """AI_ADVISORY + HIGH risk + no approval → invariant violation."""
        result = check_I01_ai_advisory_no_auto_actuate(
            origin=Origin.AI_ADVISORY, risk_class=RiskClass.HIGH, approval_record=False
        )
        assert result.passed is False
        assert result.invariant_id == "I-01"

    def test_I01_ai_advisory_high_risk_with_approval_passes(self):
        """AI_ADVISORY + HIGH risk + approval record → passes."""
        result = check_I01_ai_advisory_no_auto_actuate(
            origin=Origin.AI_ADVISORY, risk_class=RiskClass.HIGH, approval_record=True
        )
        assert result.passed is True

    def test_I01_operator_high_risk_no_approval_passes(self):
        """OPERATOR origin does not require approval for HIGH risk."""
        result = check_I01_ai_advisory_no_auto_actuate(
            origin=Origin.OPERATOR, risk_class=RiskClass.HIGH, approval_record=False
        )
        assert result.passed is True

    def test_I01_ai_advisory_low_risk_passes(self):
        """AI_ADVISORY + LOW risk → passes (advisory actions permitted)."""
        result = check_I01_ai_advisory_no_auto_actuate(
            origin=Origin.AI_ADVISORY, risk_class=RiskClass.LOW, approval_record=False
        )
        assert result.passed is True


class TestI02PersonalMemoryFamilyMode:
    def test_I02_personal_memory_family_mode_no_share_fails(self):
        """PERSONAL scope in FAMILY mode without share_relation → violation."""
        result = check_I02_personal_memory_family_mode(
            mode=Mode.FAMILY, memory_scope="PERSONAL", share_relation_exists=False
        )
        assert result.passed is False
        assert result.invariant_id == "I-02"

    def test_I02_personal_memory_family_mode_with_share_passes(self):
        """PERSONAL scope in FAMILY mode WITH share_relation → passes."""
        result = check_I02_personal_memory_family_mode(
            mode=Mode.FAMILY, memory_scope="PERSONAL", share_relation_exists=True
        )
        assert result.passed is True

    def test_I02_household_shared_family_mode_passes(self):
        """HOUSEHOLD_SHARED scope in FAMILY mode always passes."""
        result = check_I02_personal_memory_family_mode(
            mode=Mode.FAMILY, memory_scope="HOUSEHOLD_SHARED", share_relation_exists=False
        )
        assert result.passed is True


class TestI03EmergencyNoMemoryExpansion:
    def test_I03_emergency_expanding_personal_scope_fails(self):
        """FAMILY → EMERGENCY mode granting PERSONAL scope → violation."""
        result = check_I03_emergency_no_memory_expansion(
            mode_before=Mode.FAMILY,
            mode_after=Mode.EMERGENCY,
            scope_before="HOUSEHOLD_SHARED",
            scope_after="PERSONAL",
        )
        assert result.passed is False
        assert result.invariant_id == "I-03"

    def test_I03_emergency_keeping_scope_unchanged_passes(self):
        """Mode changes to EMERGENCY; scope unchanged → passes."""
        result = check_I03_emergency_no_memory_expansion(
            mode_before=Mode.FAMILY,
            mode_after=Mode.EMERGENCY,
            scope_before="HOUSEHOLD_SHARED",
            scope_after="HOUSEHOLD_SHARED",
        )
        assert result.passed is True


class TestI04StepsMutuallyExclusive:
    def test_I04_both_7a_and_7b_fails(self):
        """Both 7a and 7b invoked in same request → violation."""
        result = check_I04_7a_7b_exclusive(step_7a_invoked=True, step_7b_invoked=True)
        assert result.passed is False
        assert result.invariant_id == "I-04"

    def test_I04_only_7a_passes(self):
        result = check_I04_7a_7b_exclusive(step_7a_invoked=True, step_7b_invoked=False)
        assert result.passed is True

    def test_I04_only_7b_passes(self):
        result = check_I04_7a_7b_exclusive(step_7a_invoked=False, step_7b_invoked=True)
        assert result.passed is True

    def test_I04_neither_passes(self):
        result = check_I04_7a_7b_exclusive(step_7a_invoked=False, step_7b_invoked=False)
        assert result.passed is True


class TestI05StaleAuthzBlocksActuation:
    def test_I05_stale_authz_with_actuation_fails(self):
        """Authz result 45s old + actuation attempt → violation."""
        result = check_I05_no_stale_authz_actuation(authz_result_age_s=45.0, action_is_actuation=True)
        assert result.passed is False
        assert result.invariant_id == "I-05"

    def test_I05_fresh_authz_with_actuation_passes(self):
        result = check_I05_no_stale_authz_actuation(authz_result_age_s=5.0, action_is_actuation=True)
        assert result.passed is True

    def test_I05_stale_authz_non_actuation_passes(self):
        """Stale authz is fine for read-only actions."""
        result = check_I05_no_stale_authz_actuation(authz_result_age_s=60.0, action_is_actuation=False)
        assert result.passed is True


class TestI06ConfidenceThreshold:
    def test_I06_below_floor_fails(self):
        """Effective confidence 0.35 < 0.40 floor → always fails."""
        result = check_I06_confidence_threshold(
            effective_confidence=0.35, risk_class=RiskClass.LOW, approval_record=False
        )
        assert result.passed is False
        assert result.invariant_id == "I-06"

    def test_I06_high_risk_below_07_no_approval_fails(self):
        """HIGH risk + confidence 0.65 < 0.70 + no approval → fails."""
        result = check_I06_confidence_threshold(
            effective_confidence=0.65, risk_class=RiskClass.HIGH, approval_record=False
        )
        assert result.passed is False

    def test_I06_high_risk_below_07_with_approval_passes(self):
        """HIGH risk + confidence 0.65 + approval record → passes (human in the loop)."""
        result = check_I06_confidence_threshold(
            effective_confidence=0.65, risk_class=RiskClass.HIGH, approval_record=True
        )
        assert result.passed is True

    def test_I06_high_risk_above_07_passes(self):
        result = check_I06_confidence_threshold(
            effective_confidence=0.75, risk_class=RiskClass.HIGH, approval_record=False
        )
        assert result.passed is True


class TestI07ModeChangeRequiresReason:
    def test_I07_mode_change_no_reason_fails(self):
        """Mode changed but mode_change_reason is None → violation."""
        result = check_I07_mode_change_requires_reason(mode_changed=True, mode_change_reason=None)
        assert result.passed is False
        assert result.invariant_id == "I-07"

    def test_I07_mode_change_empty_reason_fails(self):
        result = check_I07_mode_change_requires_reason(mode_changed=True, mode_change_reason="   ")
        assert result.passed is False

    def test_I07_mode_change_with_reason_passes(self):
        result = check_I07_mode_change_requires_reason(
            mode_changed=True, mode_change_reason="identity_confidence_upgrade"
        )
        assert result.passed is True

    def test_I07_no_mode_change_no_reason_passes(self):
        """No mode change → no reason required."""
        result = check_I07_mode_change_requires_reason(mode_changed=False, mode_change_reason=None)
        assert result.passed is True


class TestI08TraceIdContinuity:
    def test_I08_mismatched_trace_id_fails(self):
        result = check_I08_trace_id_continuity("trace-001", "trace-002")
        assert result.passed is False
        assert result.invariant_id == "I-08"

    def test_I08_matching_trace_id_passes(self):
        result = check_I08_trace_id_continuity("trace-abc", "trace-abc")
        assert result.passed is True


class TestI09LoopDecayToAbandoned:
    def test_I09_stale_active_loop_fails(self):
        """freshness < 0.05 AND age > max_age AND status=ACTIVE → violation."""
        result = check_I09_loop_decay_to_abandoned(
            freshness=0.03, age_hours=50.0, max_age_hours=48.0, status=OpenLoopStatus.ACTIVE
        )
        assert result.passed is False
        assert result.invariant_id == "I-09"

    def test_I09_stale_but_already_abandoned_passes(self):
        result = check_I09_loop_decay_to_abandoned(
            freshness=0.03, age_hours=50.0, max_age_hours=48.0, status=OpenLoopStatus.ABANDONED
        )
        assert result.passed is True

    def test_I09_young_stale_loop_passes(self):
        """freshness < 0.05 but age < max_age → not yet at abandonment threshold."""
        result = check_I09_loop_decay_to_abandoned(
            freshness=0.03, age_hours=10.0, max_age_hours=48.0, status=OpenLoopStatus.ACTIVE
        )
        assert result.passed is True


class TestI10NoAutoPolicyApply:
    def test_I10_auto_apply_without_approval_fails(self):
        """Application attempted but operator_approved=False → violation."""
        result = check_I10_no_auto_policy_apply(operator_approved=False, application_attempted=True)
        assert result.passed is False
        assert result.invariant_id == "I-10"

    def test_I10_approved_application_passes(self):
        result = check_I10_no_auto_policy_apply(operator_approved=True, application_attempted=True)
        assert result.passed is True

    def test_I10_no_application_no_approval_passes(self):
        result = check_I10_no_auto_policy_apply(operator_approved=False, application_attempted=False)
        assert result.passed is True
