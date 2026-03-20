"""
State machine tests — these are part of the CI safety gate.
"""
import pytest
from orchestrator.models import (
    ApprovalEvent,
    ApprovalMode,
    Job,
    JobOrigin,
    JobState,
    RiskClass,
)
from orchestrator.state_machine import (
    InvalidTransitionError,
    PolicyViolationError,
    StateMachine,
)


@pytest.fixture
def sm():
    return StateMachine()


@pytest.fixture
def low_risk_job():
    return Job(
        type="IrrigationRun",
        requested_by="user_001",
        origin=JobOrigin.OPERATOR,
        target_asset_ids=["asset_valve_north_001"],
        risk_class=RiskClass.LOW,
        approval_mode=ApprovalMode.AUTO,
    )


@pytest.fixture
def high_risk_job():
    return Job(
        type="ValveOpen",
        requested_by="user_001",
        origin=JobOrigin.OPERATOR,
        target_asset_ids=["asset_valve_north_001"],
        risk_class=RiskClass.HIGH,
        approval_mode=ApprovalMode.OPERATOR_REQUIRED,
    )


def test_valid_transition_pending_to_validating(sm, low_risk_job):
    job = sm.transition(low_risk_job, JobState.VALIDATING)
    assert job.state == JobState.VALIDATING


def test_valid_transition_validating_to_approved(sm, low_risk_job):
    job = sm.transition(low_risk_job, JobState.VALIDATING)
    job = sm.transition(job, JobState.APPROVED)
    assert job.state == JobState.APPROVED


def test_invalid_transition_pending_to_executing(sm, low_risk_job):
    with pytest.raises(InvalidTransitionError):
        sm.transition(low_risk_job, JobState.EXECUTING)


def test_invalid_transition_completed_to_anything(sm, low_risk_job):
    job = sm.transition(low_risk_job, JobState.VALIDATING)
    job = sm.transition(job, JobState.APPROVED)
    job = sm.transition(job, JobState.EXECUTING)
    job = sm.transition(job, JobState.COMPLETED)
    with pytest.raises(InvalidTransitionError):
        sm.transition(job, JobState.PENDING)


def test_abort_from_executing(sm, high_risk_job):
    """E-stop must be able to abort from EXECUTING state."""
    job = sm.transition(high_risk_job, JobState.VALIDATING)
    job = sm.approve(job, ApprovalEvent(approved_by="operator_001"))
    job = sm.transition(job, JobState.EXECUTING)
    job = sm.abort(job, "Emergency E-stop")
    assert job.state == JobState.ABORTED
    assert "E-stop" in job.rejection_reason


# ── Fitness Function F05: no HIGH/CRITICAL with AUTO approval ──────────────

def test_f05_high_risk_auto_approval_raises_policy_violation(sm):
    """
    Architecture Fitness Function F05:
    Job with risk_class=HIGH and approval_mode=AUTO must raise PolicyViolationError.
    This test is required by the CI safety gate.
    """
    job = Job(
        type="ValveOpen",
        requested_by="user_001",
        origin=JobOrigin.OPERATOR,
        target_asset_ids=["asset_valve_north_001"],
        risk_class=RiskClass.HIGH,
        approval_mode=ApprovalMode.AUTO,  # VIOLATION
    )
    job = sm.transition(job, JobState.VALIDATING)
    with pytest.raises(PolicyViolationError):
        sm.validate(job)


def test_f05_critical_risk_auto_approval_raises_policy_violation(sm):
    """FITNESS FUNCTION F05: CRITICAL + AUTO must raise PolicyViolationError."""
    job = Job(
        type="DroneArm",
        requested_by="user_001",
        origin=JobOrigin.OPERATOR,
        target_asset_ids=["asset_drone_001"],
        risk_class=RiskClass.CRITICAL,
        approval_mode=ApprovalMode.AUTO,  # VIOLATION
    )
    job = sm.transition(job, JobState.VALIDATING)
    with pytest.raises(PolicyViolationError):
        sm.validate(job)


def test_ai_advisory_medium_risk_requires_operator_approval(sm):
    """AI advisory jobs with MEDIUM risk must require operator approval."""
    job = Job(
        type="IrrigationRun",
        requested_by="model_router",
        origin=JobOrigin.AI_ADVISORY,
        target_asset_ids=["asset_valve_north_001"],
        risk_class=RiskClass.MEDIUM,
        approval_mode=ApprovalMode.AUTO,  # VIOLATION for AI advisory
    )
    job = sm.transition(job, JobState.VALIDATING)
    with pytest.raises(PolicyViolationError):
        sm.validate(job)


def test_operator_low_risk_auto_approval_passes(sm):
    """Operator LOW risk with AUTO approval is valid."""
    job = Job(
        type="FanControl",
        requested_by="user_001",
        origin=JobOrigin.OPERATOR,
        target_asset_ids=["asset_fan_zone_a_001"],
        risk_class=RiskClass.LOW,
        approval_mode=ApprovalMode.AUTO,
    )
    job = sm.transition(job, JobState.VALIDATING)
    passed, reason = sm.validate(job)
    assert passed is True
    assert reason is None
