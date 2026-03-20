"""
Job state machine — deterministic transitions, guard conditions, retry logic.
This is the core safety mechanism. No ad-hoc execution.
"""
from __future__ import annotations

import structlog
from datetime import datetime

from .models import (
    ApprovalEvent,
    ApprovalMode,
    Job,
    JobOrigin,
    JobState,
    RiskClass,
)
from .policy import evaluate_approval_mode, check_preconditions

logger = structlog.get_logger(__name__)


class PolicyViolationError(Exception):
    """Raised when a policy check fails — caught by CI safety gate."""
    pass


class InvalidTransitionError(Exception):
    """Raised when a state transition is not permitted."""
    pass


class StateMachine:
    """
    Enforces job state transitions. All transitions are logged.
    Only orchestrator service instantiates this; no other service may call it.
    """

    ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
        JobState.PENDING: {JobState.VALIDATING},
        JobState.VALIDATING: {JobState.APPROVED, JobState.REJECTED},
        JobState.APPROVED: {JobState.EXECUTING, JobState.REJECTED},
        JobState.EXECUTING: {JobState.COMPLETED, JobState.FAILED, JobState.ABORTED},
        # Any state can be ABORTED by emergency e-stop
        JobState.COMPLETED: set(),
        JobState.FAILED: set(),
        JobState.REJECTED: set(),
        JobState.ABORTED: set(),
    }

    def transition(self, job: Job, target_state: JobState, *, reason: str | None = None) -> Job:
        """
        Perform a state transition. Returns the updated job.
        Raises InvalidTransitionError if the transition is not permitted.
        """
        # Emergency ABORT from any non-terminal state
        if target_state == JobState.ABORTED and job.state not in (
            JobState.COMPLETED, JobState.FAILED, JobState.REJECTED, JobState.ABORTED
        ):
            return self._do_transition(job, target_state, reason=reason)

        allowed = self.ALLOWED_TRANSITIONS.get(job.state, set())
        if target_state not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition job {job.job_id} from {job.state} to {target_state}"
            )
        return self._do_transition(job, target_state, reason=reason)

    def _do_transition(self, job: Job, target: JobState, *, reason: str | None = None) -> Job:
        prev_state = job.state
        job.state = target
        job.updated_at = datetime.utcnow()
        if target in (JobState.COMPLETED, JobState.FAILED, JobState.ABORTED, JobState.REJECTED):
            job.completed_at = datetime.utcnow()
        if reason and target in (JobState.FAILED, JobState.REJECTED, JobState.ABORTED):
            job.rejection_reason = reason
        logger.info(
            "job_state_transition",
            job_id=job.job_id,
            from_state=prev_state,
            to_state=target,
            reason=reason,
        )
        return job

    def validate(self, job: Job) -> tuple[bool, str | None]:
        """
        Run VALIDATING checks. Returns (passed, rejection_reason).
        Enforces: no HIGH/CRITICAL job with AUTO approval (fitness function F05).
        """
        # F05: no high-risk job with AUTO approval
        if job.risk_class in (RiskClass.HIGH, RiskClass.CRITICAL):
            if job.approval_mode == ApprovalMode.AUTO:
                raise PolicyViolationError(
                    f"Job {job.job_id} has risk_class={job.risk_class} with approval_mode=AUTO. "
                    "This violates architecture fitness function F05."
                )

        # AI advisory jobs: max auto-approval is LOW
        if job.origin == JobOrigin.AI_ADVISORY:
            if job.risk_class in (RiskClass.MEDIUM, RiskClass.HIGH, RiskClass.CRITICAL):
                if job.approval_mode != ApprovalMode.OPERATOR_REQUIRED:
                    raise PolicyViolationError(
                        f"AI advisory job {job.job_id} with risk_class={job.risk_class} "
                        "must have approval_mode=OPERATOR_REQUIRED."
                    )

        # Check preconditions
        passed, reason = check_preconditions(job)
        return passed, reason

    def approve(self, job: Job, approval: ApprovalEvent) -> Job:
        """
        Record an operator approval. Only valid from VALIDATING or APPROVED state
        where approval is pending.
        """
        if job.state != JobState.VALIDATING and job.approval_mode == ApprovalMode.OPERATOR_REQUIRED:
            raise InvalidTransitionError(
                f"Job {job.job_id} cannot be approved in state {job.state}"
            )
        job.approval_event = approval
        logger.info("job_approved", job_id=job.job_id, approved_by=approval.approved_by)
        return self.transition(job, JobState.APPROVED)

    def reject(self, job: Job, reason: str) -> Job:
        """Operator or policy rejects the job."""
        return self.transition(job, JobState.REJECTED, reason=reason)

    def abort(self, job: Job, reason: str) -> Job:
        """Emergency or E-stop aborts the job from any non-terminal state."""
        return self.transition(job, JobState.ABORTED, reason=reason)
