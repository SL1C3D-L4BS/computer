"""
Command policy evaluation — approval mode derivation and precondition checks.
"""
from __future__ import annotations

from .models import ApprovalMode, Job, JobOrigin, RiskClass


def evaluate_approval_mode(origin: JobOrigin, risk_class: RiskClass) -> ApprovalMode:
    """
    Derive the required approval mode from origin × risk_class.
    This is the canonical policy matrix.
    """
    if risk_class == RiskClass.INFORMATIONAL:
        return ApprovalMode.NONE

    if risk_class == RiskClass.CRITICAL:
        return ApprovalMode.OPERATOR_CONFIRM_TWICE

    if risk_class == RiskClass.HIGH:
        return ApprovalMode.OPERATOR_REQUIRED

    if risk_class == RiskClass.MEDIUM:
        if origin == JobOrigin.AI_ADVISORY:
            # AI advisory medium-risk always requires operator
            return ApprovalMode.OPERATOR_REQUIRED
        return ApprovalMode.AUTO_WITH_AUDIT

    if risk_class == RiskClass.LOW:
        if origin == JobOrigin.AI_ADVISORY:
            return ApprovalMode.AUTO_WITH_AUDIT
        return ApprovalMode.AUTO

    return ApprovalMode.OPERATOR_REQUIRED  # safe default


def check_preconditions(job: Job) -> tuple[bool, str | None]:
    """
    Evaluate job preconditions. Returns (all_satisfied, failure_reason).
    In a real implementation, this calls digital-twin to check asset state.
    """
    for precondition in job.preconditions:
        if precondition.satisfied is False:
            return False, f"Precondition not satisfied: {precondition.description}"
        # None means "not yet checked" — treat as passed in this implementation
        # Production: query digital-twin API for asset state checks
    return True, None
