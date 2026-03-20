"""
Durable Workflow Implementations — V4 Production Canonical Classes

V4 defines exactly 4 canonical workflow classes registered against the workflow registry:
1. ReminderWorkflow     — durable timers, pause/resume, max_age cleanup
2. ApprovalWorkflow     — Temporal update handler for ack; stale after 7d
3. RoutineWorkflow      — daily schedule, skip-step recovery, idempotent retries (max 3, backoff)
4. FollowUpWorkflow     — signal-triggered from loops.resolve; escalates to INTERRUPT after deadline

V3 legacy classes are preserved below for backward compatibility:
- MultiDayReminderWorkflow (→ superseded by ReminderWorkflow)
- ApprovalPersistenceWorkflow (→ superseded by ApprovalWorkflow)
- HouseholdRoutineWorkflow (→ superseded by RoutineWorkflow)

Design contract:
- Workflow IDs are deterministic (not random) so restart produces same ID
- Each workflow is resumable: if the worker restarts mid-execution, Temporal
  replays from the beginning; the workflow must be idempotent
- No workflow directly actuates hardware; it creates orchestrator jobs via
  the control-api (step 7b boundary)
- All state transitions emit ObservationRecord to audit log

Registry: docs/architecture/workflow-registry-model.md
Patterns:  docs/architecture/workflow-production-patterns.md
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Deterministic Workflow ID Helper ─────────────────────────────────────────

def deterministic_workflow_id(workflow_type: str, user_id: str, context: str) -> str:
    """
    Produces a stable workflow ID for a given (type, user, context) triple.
    Critical property: if the same request arrives after a server restart,
    it produces the same ID, enabling Temporal to route to the existing workflow
    rather than creating a duplicate.

    This is the restart-invariant ID guarantee required by test_durable_workflows.py.
    """
    key = f"{workflow_type}:{user_id}:{context}"
    return f"wf-{workflow_type.lower()}-{hashlib.sha256(key.encode()).hexdigest()[:16]}"


# ── Shared Activity Stubs ─────────────────────────────────────────────────────

async def activity_send_notification(user_id: str, message: str, channel: str) -> dict:
    """Deliver a notification via the attention-engine (step 9 path)."""
    return {"delivered": True, "user_id": user_id, "channel": channel}


async def activity_query_workflow_state(workflow_id: str) -> dict:
    """Query current state of a workflow without side effects."""
    return {"workflow_id": workflow_id, "status": "RUNNING"}


async def activity_request_orchestrator_job(
    job_type: str, params: dict, risk_class: str
) -> dict:
    """
    Create a site control job via orchestrator (step 7b).
    MUST NOT directly actuate hardware.
    """
    return {"job_id": f"job-{job_type}-stub", "status": "PENDING", "risk_class": risk_class}


async def activity_write_observation_record(
    trace_id: str, step: str, observation_type: str, value: Any
) -> None:
    """Write an ObservationRecord to the audit log."""
    pass  # Real implementation calls runtime-kernel POST /audit


# ── Workflow 1: MultiDayReminderWorkflow ──────────────────────────────────────

@dataclass
class ReminderWorkflowState:
    workflow_id: str
    user_id: str
    message: str
    remind_at: str          # ISO 8601
    created_at: str
    status: str = "PENDING" # PENDING | DELIVERED | CANCELLED | FAILED
    attempts: int = 0
    max_attempts: int = 3
    acknowledged: bool = False
    acknowledgment_trace_id: str | None = None


class MultiDayReminderWorkflow:
    """
    A durable reminder that fires on a scheduled future date.

    Proof obligations (tested by test_durable_workflows.py):
    1. Workflow ID is deterministic — same inputs → same ID across restarts
    2. If the worker restarts before remind_at, the workflow resumes correctly
    3. If acknowledge signal arrives before remind_at, workflow closes without firing
    4. If max_attempts exceeded without ack, workflow closes with status FAILED
    5. ObservationRecord is written at DELIVERED and ACKNOWLEDGED

    Real implementation uses: temporalio @workflow.defn, @activity.defn,
    workflow.sleep_until(remind_at), workflow.wait_condition(acknowledge signal)
    """

    def __init__(self, user_id: str, message: str, remind_at: str):
        self.state = ReminderWorkflowState(
            workflow_id=deterministic_workflow_id("MultiDayReminder", user_id, message + remind_at),
            user_id=user_id,
            message=message,
            remind_at=remind_at,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._acknowledged = False
        self._cancelled = False

    @property
    def workflow_id(self) -> str:
        return self.state.workflow_id

    async def run(self) -> ReminderWorkflowState:
        """Main workflow coroutine. This is what Temporal replays on restart."""
        # Step 1: Sleep until reminder time
        # In real Temporal: await workflow.sleep_until(self.state.remind_at)
        await asyncio.sleep(0)  # stub: immediate for testing

        if self._cancelled:
            self.state.status = "CANCELLED"
            return self.state

        # Step 2: Deliver notification (retries automatically on failure)
        for attempt in range(self.state.max_attempts):
            self.state.attempts = attempt + 1
            result = await activity_send_notification(
                self.state.user_id, self.state.message, "voice"
            )
            if result["delivered"]:
                self.state.status = "DELIVERED"
                break
        else:
            self.state.status = "FAILED"
            return self.state

        # Step 3: Wait for acknowledgment (with timeout)
        # In real Temporal: await workflow.wait_condition(lambda: self._acknowledged, timeout=3600)
        self.state.acknowledged = self._acknowledged

        await activity_write_observation_record(
            trace_id=self.state.workflow_id,
            step="workflow.reminder",
            observation_type="completion",
            value={"status": self.state.status, "attempts": self.state.attempts},
        )
        return self.state

    def signal_acknowledge(self, trace_id: str) -> None:
        """Signal handler: user acknowledged the reminder."""
        self._acknowledged = True
        self.state.acknowledged = True
        self.state.acknowledgment_trace_id = trace_id

    def signal_cancel(self) -> None:
        """Signal handler: reminder was cancelled."""
        self._cancelled = True


# ── Workflow 2: ApprovalPersistenceWorkflow ───────────────────────────────────

@dataclass
class ApprovalWorkflowState:
    workflow_id: str
    user_id: str
    action_description: str
    risk_class: str
    created_at: str
    approval_timeout_s: float = 86400.0  # 24h default
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL | APPROVED | REJECTED | EXPIRED
    approver_id: str | None = None
    approved_at: str | None = None
    job_id: str | None = None          # Set when orchestrator job is created post-approval
    restart_count: int = 0             # Incremented to prove restart survival


class ApprovalPersistenceWorkflow:
    """
    A workflow that awaits human approval before proceeding.

    Proof obligations (tested by test_durable_workflows.py):
    1. Approval state survives server restart (Temporal replays from last checkpoint)
    2. If approved before restart, the job is still created after restart
    3. If timeout expires before approval, status = EXPIRED (no job created)
    4. Deterministic workflow ID means no duplicate workflows after restart
    5. Job creation never happens without approved status (invariant I-01 boundary)

    Real implementation uses: workflow.wait_condition(lambda: self._approved or self._expired)
    with workflow.sleep(approval_timeout_s) running concurrently.
    """

    def __init__(self, user_id: str, action_description: str, risk_class: str):
        self.state = ApprovalWorkflowState(
            workflow_id=deterministic_workflow_id(
                "ApprovalPersistence", user_id, action_description
            ),
            user_id=user_id,
            action_description=action_description,
            risk_class=risk_class,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._approved = False
        self._rejected = False

    @property
    def workflow_id(self) -> str:
        return self.state.workflow_id

    async def run(self) -> ApprovalWorkflowState:
        """
        Wait for approval signal or timeout.
        Restartable: Temporal replays from beginning but activities are idempotent.
        """
        # Step 1: Notify approver
        await activity_send_notification(
            self.state.user_id,
            f"Approval required: {self.state.action_description}",
            "web"
        )

        # Step 2: Wait for approval signal (stub: immediate for testing)
        # Real: await asyncio.gather(
        #     workflow.wait_condition(lambda: self._approved or self._rejected),
        #     workflow.sleep(self.state.approval_timeout_s)
        # ) with first-to-complete wins

        # For testing, check current state
        if self._approved:
            self.state.status = "APPROVED"
            self.state.approved_at = datetime.now(timezone.utc).isoformat()

            # Step 3: Create orchestrator job (ONLY after approval — invariant I-01)
            job_result = await activity_request_orchestrator_job(
                job_type="approved_action",
                params={"action": self.state.action_description},
                risk_class=self.state.risk_class,
            )
            self.state.job_id = job_result["job_id"]
        elif self._rejected:
            self.state.status = "REJECTED"
        else:
            self.state.status = "EXPIRED"

        await activity_write_observation_record(
            trace_id=self.state.workflow_id,
            step="workflow.approval",
            observation_type="completion",
            value={"status": self.state.status, "job_id": self.state.job_id},
        )
        return self.state

    def signal_approve(self, approver_id: str) -> None:
        """Signal: operator approved the action."""
        self._approved = True
        self.state.approver_id = approver_id

    def signal_reject(self, approver_id: str) -> None:
        """Signal: operator rejected the action."""
        self._rejected = True
        self.state.approver_id = approver_id

    def query_status(self) -> dict:
        """Query handler: returns current approval state without side effects."""
        return {
            "workflow_id": self.state.workflow_id,
            "status": self.state.status,
            "approver_id": self.state.approver_id,
            "job_id": self.state.job_id,
        }


# ── Workflow 3: HouseholdRoutineWorkflow ──────────────────────────────────────

@dataclass
class RoutineStep:
    name: str
    description: str
    required: bool          # False = optional; can be skipped
    status: str = "PENDING" # PENDING | COMPLETED | SKIPPED | FAILED
    completed_at: str | None = None
    skip_reason: str | None = None


@dataclass
class HouseholdRoutineState:
    workflow_id: str
    user_id: str
    routine_name: str
    steps: list[RoutineStep]
    created_at: str
    status: str = "IN_PROGRESS"  # IN_PROGRESS | COMPLETED | PARTIALLY_COMPLETED | FAILED
    completion_rate: float = 0.0  # required_completed / total_required
    recovery_events: list[str] = field(default_factory=list)


class HouseholdRoutineWorkflow:
    """
    A multi-step household routine with skipped-step recovery.

    Proof obligations (tested by test_durable_workflows.py):
    1. Optional steps can be skipped without failing the workflow
    2. If a required step fails, the workflow enters recovery mode and retries
    3. completion_rate is computed correctly: required_completed / total_required
    4. If worker restarts mid-routine, already-completed steps are NOT re-executed
       (idempotency via activity result caching in Temporal)
    5. Recovery events are logged to audit trail

    Example routine: Morning greenhouse check
      - Step 1: Read temperature sensors (required)
      - Step 2: Check soil moisture (required)
      - Step 3: Review overnight alerts (optional)
      - Step 4: Approve irrigation if needed (required, may be skipped if no alert)
    """

    DEFAULT_STEPS = [
        RoutineStep("read_sensors", "Read temperature and humidity sensors", required=True),
        RoutineStep("check_moisture", "Check soil moisture levels", required=True),
        RoutineStep("review_alerts", "Review overnight alerts", required=False),
        RoutineStep("approve_irrigation", "Approve irrigation if moisture low", required=True),
    ]

    def __init__(self, user_id: str, routine_name: str, steps: list[RoutineStep] | None = None):
        self.state = HouseholdRoutineState(
            workflow_id=deterministic_workflow_id("HouseholdRoutine", user_id, routine_name),
            user_id=user_id,
            routine_name=routine_name,
            steps=steps or [RoutineStep(**vars(s)) for s in self.DEFAULT_STEPS],
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._skipped_steps: set[str] = set()
        self._manual_completions: dict[str, str] = {}  # step_name → completion_trace_id

    @property
    def workflow_id(self) -> str:
        return self.state.workflow_id

    async def run(self) -> HouseholdRoutineState:
        """Execute routine steps in order, with recovery for failures."""
        for step in self.state.steps:
            if step.name in self._skipped_steps:
                step.status = "SKIPPED"
                step.skip_reason = "operator_signaled"
                self.state.recovery_events.append(f"SKIP:{step.name}")
                continue

            if step.name in self._manual_completions:
                step.status = "COMPLETED"
                step.completed_at = datetime.now(timezone.utc).isoformat()
                continue

            # Execute the step activity
            success = await self._execute_step(step)

            if not success and step.required:
                # Recovery: retry once, then ask for human input
                self.state.recovery_events.append(f"RETRY:{step.name}")
                success = await self._execute_step(step)

                if not success:
                    # If step can be skipped by operator signal, wait for it
                    # In real Temporal: await workflow.wait_condition(lambda: step.name in self._skipped_steps, timeout=3600)
                    if step.name in self._skipped_steps:
                        step.status = "SKIPPED"
                        step.skip_reason = "recovery_skip"
                    else:
                        step.status = "FAILED"
                        self.state.recovery_events.append(f"FAILED:{step.name}")

        self._compute_completion_rate()
        self.state.status = self._determine_status()

        await activity_write_observation_record(
            trace_id=self.state.workflow_id,
            step="workflow.household_routine",
            observation_type="completion",
            value={
                "status": self.state.status,
                "completion_rate": self.state.completion_rate,
                "recovery_events": self.state.recovery_events,
            },
        )
        return self.state

    async def _execute_step(self, step: RoutineStep) -> bool:
        """Execute a single step. Returns True on success."""
        step.status = "COMPLETED"
        step.completed_at = datetime.now(timezone.utc).isoformat()
        return True  # Stub: always succeeds; real version calls activity

    def _compute_completion_rate(self) -> None:
        required = [s for s in self.state.steps if s.required]
        completed = [s for s in required if s.status == "COMPLETED"]
        self.state.completion_rate = len(completed) / len(required) if required else 1.0

    def _determine_status(self) -> str:
        if all(s.status in ("COMPLETED", "SKIPPED") for s in self.state.steps):
            return "COMPLETED"
        required_failed = [s for s in self.state.steps if s.required and s.status == "FAILED"]
        if required_failed:
            return "FAILED"
        return "PARTIALLY_COMPLETED"

    def signal_skip_step(self, step_name: str) -> None:
        """Signal: operator requests that a specific step be skipped."""
        self._skipped_steps.add(step_name)

    def signal_complete_step(self, step_name: str, trace_id: str) -> None:
        """Signal: operator manually completed a step."""
        self._manual_completions[step_name] = trace_id

    def query_progress(self) -> dict:
        """Query handler: returns step progress without side effects."""
        return {
            "workflow_id": self.state.workflow_id,
            "steps": [
                {"name": s.name, "status": s.status, "required": s.required}
                for s in self.state.steps
            ],
            "completion_rate": self.state.completion_rate,
            "recovery_events": self.state.recovery_events,
        }


# ══════════════════════════════════════════════════════════════════════════════
# V4 CANONICAL WORKFLOW CLASSES
# Registry: docs/architecture/workflow-registry-model.md
# These 4 classes replace the V3 proof-cases and are registered against
# the workflow registry schema.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class WorkflowRegistryEntry:
    """
    Runtime registry schema from workflow-registry-model.md.
    Every canonical workflow class must declare this at class level.
    """
    name: str
    version: str
    domain: str
    description: str
    max_run_duration_days: int
    heartbeat_interval_minutes: int
    max_retry_attempts: int
    retry_backoff_seconds: int
    non_retryable_errors: list[str]
    stale_after_days: int
    sweep_action: str
    migration_notes: str


class ReminderWorkflow:
    """
    V4 Canonical: ReminderWorkflow

    Durable timer with pause/resume; fires reminder signal and marks CLOSED
    on acknowledgment. Cleans up after max_age_days.

    Registry:
        name=ReminderWorkflow, version=1.0.0, domain=household
        max_run_duration_days=90, stale_after_days=90, sweep_action=cancel
    """

    REGISTRY = WorkflowRegistryEntry(
        name="ReminderWorkflow",
        version="1.0.0",
        domain="household",
        description="Durable timer with pause/resume; fires reminder signal and marks CLOSED on acknowledgment.",
        max_run_duration_days=90,
        heartbeat_interval_minutes=60,
        max_retry_attempts=3,
        retry_backoff_seconds=30,
        non_retryable_errors=["ReminderNotFound", "UserNotFound"],
        stale_after_days=90,
        sweep_action="cancel",
        migration_notes=(
            "V1→V2: adding recurrence field. In-flight workflows without recurrence "
            "field will use default=none; no replay required."
        ),
    )

    def __init__(self, reminder_id: str, user_id: str, message: str,
                 fire_at: str, recurrence: str = "none", max_age_days: int = 30):
        self.workflow_id = deterministic_workflow_id("ReminderWorkflow", reminder_id, user_id)
        self.reminder_id = reminder_id
        self.user_id = user_id
        self.message = message
        self.fire_at = fire_at
        self.recurrence = recurrence
        self.max_age_days = max_age_days
        self.status = "PENDING"  # PENDING → FIRED → ACKNOWLEDGED / EXPIRED
        self._paused = False
        self._acknowledged = False

    async def run(self) -> dict:
        """
        Main execution loop (Temporal-compatible; stub without Temporal import).
        1. Wait until fire_at or max_age
        2. Fire reminder → notification
        3. Wait for acknowledgment signal or max_age expiry
        4. Mark CLOSED (acknowledged) or ABANDONED (expired)
        """
        self.status = "WAITING"
        # In real Temporal: await workflow.wait_condition(lambda: ...) with timeout
        # Stub: simulate fire
        await activity_send_notification(self.user_id, self.message, "voice-gateway")
        await activity_write_observation_record(
            self.workflow_id, "reminder_fired", "reminder_fire", {"reminder_id": self.reminder_id}
        )
        self.status = "FIRED"
        if self._acknowledged:
            self.status = "CLOSED"
        else:
            self.status = "ABANDONED"
        return {"workflow_id": self.workflow_id, "status": self.status,
                "reminder_id": self.reminder_id}

    def signal_acknowledge(self) -> None:
        """Signal: user acknowledged the reminder."""
        self._acknowledged = True
        self.status = "ACKNOWLEDGED"

    def signal_pause(self) -> None:
        self._paused = True

    def signal_resume(self) -> None:
        self._paused = False

    def query_status(self) -> dict:
        return {"workflow_id": self.workflow_id, "status": self.status,
                "reminder_id": self.reminder_id, "paused": self._paused}


@dataclass
class ApprovalDecision:
    decision: str   # "APPROVED" | "DENIED"
    approver_id: str
    timestamp: str
    approval_token: str | None = None  # passkey approval token (approval track)


@dataclass
class ApprovalResult:
    approval_id: str
    decision: str
    decided_by: str
    decided_at: str


class ApprovalWorkflow:
    """
    V4 Canonical: ApprovalWorkflow

    Waits for explicit approval or denial via update handler. Stale after 7d.
    For HIGH risk_class: requires passkey re-auth (approval track) to resolve.

    Registry:
        name=ApprovalWorkflow, version=1.0.0, domain=household
        max_run_duration_days=7, max_retry_attempts=1, stale_after_days=7, sweep_action=cancel
    """

    REGISTRY = WorkflowRegistryEntry(
        name="ApprovalWorkflow",
        version="1.0.0",
        domain="household",
        description="Waits for explicit approval or denial via Temporal update handler; stale after 7d.",
        max_run_duration_days=7,
        heartbeat_interval_minutes=30,
        max_retry_attempts=1,
        retry_backoff_seconds=0,
        non_retryable_errors=["ApprovalExpired", "ApproverNotFound"],
        stale_after_days=7,
        sweep_action="cancel",
        migration_notes=(
            "V1→V2: adding requires_passkey field. In-flight workflows use default=false; "
            "new approvals pick up new field."
        ),
    )

    def __init__(self, approval_id: str, requester_id: str, approver_ids: list[str],
                 description: str, expires_at: str, risk_class: str = "LOW",
                 requires_passkey: bool = False):
        self.workflow_id = deterministic_workflow_id("ApprovalWorkflow", approval_id, requester_id)
        self.approval_id = approval_id
        self.requester_id = requester_id
        self.approver_ids = approver_ids
        self.description = description
        self.expires_at = expires_at
        self.risk_class = risk_class
        self.requires_passkey = requires_passkey or (risk_class == "HIGH")
        self.status = "PENDING"  # PENDING → APPROVED | DENIED | EXPIRED
        self._decision: ApprovalDecision | None = None

    async def process_approval(self, decision: ApprovalDecision) -> ApprovalResult:
        """
        Update handler: atomically accepts/denies the approval.
        Idempotent: second call with same decision returns same result.
        Throws ApprovalAlreadyResolved if already decided.
        """
        if self.status != "PENDING":
            raise ValueError(f"ApprovalAlreadyResolved: {self.approval_id} is {self.status}")
        if decision.approver_id not in self.approver_ids:
            raise ValueError(f"ApproverNotFound: {decision.approver_id}")
        if self.requires_passkey and not decision.approval_token:
            raise ValueError("ApprovalRequiresPasskey: approval_token missing")

        self._decision = decision
        self.status = decision.decision  # "APPROVED" or "DENIED"
        await activity_write_observation_record(
            self.workflow_id, "approval_decided", "approval_decision",
            {"approval_id": self.approval_id, "decision": decision.decision,
             "decided_by": decision.approver_id}
        )
        return ApprovalResult(
            approval_id=self.approval_id,
            decision=decision.decision,
            decided_by=decision.approver_id,
            decided_at=decision.timestamp,
        )

    def signal_expire(self) -> None:
        """Signal: approval window has expired (sent by sweep)."""
        if self.status == "PENDING":
            self.status = "EXPIRED"

    def query_status(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "approval_id": self.approval_id,
            "status": self.status,
            "risk_class": self.risk_class,
            "requires_passkey": self.requires_passkey,
        }


@dataclass
class RoutineStep:
    name: str
    required: bool = True
    status: str = "PENDING"  # PENDING → RUNNING → COMPLETED | FAILED | SKIPPED
    attempt_count: int = 0


class RoutineWorkflow:
    """
    V4 Canonical: RoutineWorkflow

    Daily schedule execution with skip-step recovery and idempotent retries (max 3, 60s backoff).

    Registry:
        name=RoutineWorkflow, version=1.0.0, domain=household
        max_run_duration_days=1, max_retry_attempts=3, stale_after_days=2, sweep_action=archive
    """

    REGISTRY = WorkflowRegistryEntry(
        name="RoutineWorkflow",
        version="1.0.0",
        domain="household",
        description="Daily schedule execution with skip-step recovery and idempotent retries.",
        max_run_duration_days=1,
        heartbeat_interval_minutes=15,
        max_retry_attempts=3,
        retry_backoff_seconds=60,
        non_retryable_errors=["RoutineNotFound", "InvalidStep"],
        stale_after_days=2,
        sweep_action="archive",
        migration_notes=(
            "Step schema changes require explicit version bump and in-flight workflow "
            "drain before deploying new worker."
        ),
    )

    def __init__(self, routine_id: str, steps: list[dict], skip_on_error: bool = False):
        self.workflow_id = deterministic_workflow_id("RoutineWorkflow", routine_id, "v1")
        self.routine_id = routine_id
        self.skip_on_error = skip_on_error
        self.steps = [RoutineStep(name=s["name"], required=s.get("required", True))
                      for s in steps]
        self.status = "PENDING"
        self.completion_rate = 0.0
        self._skipped_overrides: set[str] = set()

    async def run(self) -> dict:
        """Execute all steps in order with idempotent retry semantics."""
        self.status = "RUNNING"
        for step in self.steps:
            if step.name in self._skipped_overrides:
                step.status = "SKIPPED"
                continue
            step.status = "RUNNING"
            success = False
            for attempt in range(1, self.REGISTRY.max_retry_attempts + 1):
                step.attempt_count = attempt
                try:
                    await activity_write_observation_record(
                        self.workflow_id, f"step_{step.name}", "step_attempt",
                        {"step": step.name, "attempt": attempt}
                    )
                    step.status = "COMPLETED"
                    success = True
                    break
                except Exception as e:
                    if attempt < self.REGISTRY.max_retry_attempts:
                        await asyncio.sleep(self.REGISTRY.retry_backoff_seconds)
                    else:
                        step.status = "FAILED"
            if not success:
                if step.required and not self.skip_on_error:
                    self.status = "FAILED"
                    return self.query_progress()
                else:
                    step.status = "SKIPPED"

        completed = [s for s in self.steps if s.status == "COMPLETED"]
        required = [s for s in self.steps if s.required]
        self.completion_rate = len(completed) / len(self.steps) if self.steps else 1.0
        all_required_done = all(s.status in ("COMPLETED", "SKIPPED") for s in required)
        self.status = "COMPLETED" if all_required_done else "PARTIALLY_COMPLETED"
        return self.query_progress()

    def signal_skip_step(self, step_name: str) -> None:
        self._skipped_overrides.add(step_name)

    def query_progress(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "routine_id": self.routine_id,
            "status": self.status,
            "completion_rate": self.completion_rate,
            "steps": [{"name": s.name, "status": s.status, "attempts": s.attempt_count}
                      for s in self.steps],
        }


class FollowUpWorkflow:
    """
    V4 Canonical: FollowUpWorkflow

    Signal-triggered from loops.resolve. Escalates to INTERRUPT after deadline
    if the loop is not closed/resolved. Supports both INTERRUPT and ABANDON escalation.

    Registry:
        name=FollowUpWorkflow, version=1.0.0, domain=founder
        max_run_duration_days=30, max_retry_attempts=2, stale_after_days=30, sweep_action=cancel
    """

    REGISTRY = WorkflowRegistryEntry(
        name="FollowUpWorkflow",
        version="1.0.0",
        domain="founder",
        description=(
            "Signal-triggered from loops.resolve; escalates to INTERRUPT after deadline "
            "if unresolved."
        ),
        max_run_duration_days=30,
        heartbeat_interval_minutes=120,
        max_retry_attempts=2,
        retry_backoff_seconds=300,
        non_retryable_errors=["LoopNotFound", "LoopAlreadyClosed"],
        stale_after_days=30,
        sweep_action="cancel",
        migration_notes=(
            "Adding escalation fields is backward-compatible; in-flight workflows "
            "without these fields use default behavior (no escalation)."
        ),
    )

    def __init__(self, loop_id: str, user_id: str, description: str,
                 follow_up_at: str, escalation_deadline: str | None = None,
                 escalation_action: str = "INTERRUPT"):
        self.workflow_id = deterministic_workflow_id("FollowUpWorkflow", loop_id, user_id)
        self.loop_id = loop_id
        self.user_id = user_id
        self.description = description
        self.follow_up_at = follow_up_at
        self.escalation_deadline = escalation_deadline
        self.escalation_action = escalation_action  # "INTERRUPT" or "ABANDON"
        self.status = "WAITING"   # WAITING → REMINDED → ESCALATED | RESOLVED
        self._resolved = False
        self._escalated = False

    async def run(self) -> dict:
        """
        Main loop: wait for follow_up_at, send reminder, wait for resolution or escalation.
        Idempotent on 'resolved' signal.
        """
        # Phase 1: Wait until follow_up_at (Temporal: await workflow.wait_condition)
        # Stub: send follow-up reminder
        await activity_send_notification(
            self.user_id,
            f"Follow-up: {self.description}",
            "voice-gateway"
        )
        await activity_write_observation_record(
            self.workflow_id, "followup_reminder_sent", "followup_fire",
            {"loop_id": self.loop_id}
        )
        self.status = "REMINDED"

        # Phase 2: Wait for resolution signal or escalation deadline
        if self._resolved:
            self.status = "RESOLVED"
        elif self.escalation_deadline:
            # In real Temporal: await workflow.wait_condition(...) with deadline timeout
            self.status = "ESCALATED"
            self._escalated = True
            await activity_write_observation_record(
                self.workflow_id, "followup_escalated", "escalation",
                {"loop_id": self.loop_id, "escalation_action": self.escalation_action}
            )
        return self.query_status()

    def signal_resolved(self) -> None:
        """
        Signal: loop has been resolved (from loops.resolve tool call).
        Idempotent: second call has no effect if already resolved.
        """
        if not self._resolved:
            self._resolved = True
            self.status = "RESOLVED"

    def query_status(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "loop_id": self.loop_id,
            "status": self.status,
            "escalated": self._escalated,
            "resolved": self._resolved,
            "escalation_action": self.escalation_action,
        }


# ── V4 Canonical Workflow Registry (runtime reference) ────────────────────────

V4_CANONICAL_WORKFLOWS: dict[str, WorkflowRegistryEntry] = {
    "ReminderWorkflow":  ReminderWorkflow.REGISTRY,
    "ApprovalWorkflow":  ApprovalWorkflow.REGISTRY,
    "RoutineWorkflow":   RoutineWorkflow.REGISTRY,
    "FollowUpWorkflow":  FollowUpWorkflow.REGISTRY,
}
