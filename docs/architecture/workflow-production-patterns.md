# Workflow Production Patterns

**Status:** Active  
**Version:** 1.0.0  
**Owner:** Workflow-runtime maintainer

---

## Overview

This document defines production patterns for the 4 canonical workflow classes. Each pattern ensures restart-invariance, bounded retry behavior, safe cleanup, and zero-downtime worker upgrades.

---

## Restart-Invariant ID Convention

Every workflow instance must be constructed with a deterministic ID that survives system restart, duplicate invocation, and retry:

```python
def deterministic_workflow_id(workflow_type: str, entity_id: str, context: str = "") -> str:
    """
    Generate a stable, collision-safe workflow ID.

    Format: {workflow_type}/{entity_id}/{sha256_prefix_of_context}
    
    Examples:
      ReminderWorkflow/reminder-abc123/a1b2c3d4
      ApprovalWorkflow/approval-xyz789/
      FollowUpWorkflow/loop-def456/deadline-2026-04-01
    """
    import hashlib
    ctx_hash = hashlib.sha256(context.encode()).hexdigest()[:8] if context else ""
    parts = [workflow_type, entity_id]
    if ctx_hash:
        parts.append(ctx_hash)
    return "/".join(parts)
```

A duplicate `StartWorkflow` call with the same ID is idempotent — Temporal returns the existing workflow handle. This prevents phantom duplicate workflows on service restart.

---

## Retry Caps and Timeout Distributions per Class

| Class | Max attempts | Backoff | Max duration | Heartbeat |
| --- | --- | --- | --- | --- |
| `ReminderWorkflow` | 3 | 30s | 90 days | 60 min |
| `ApprovalWorkflow` | 1 | N/A | 7 days | 30 min |
| `RoutineWorkflow` | 3 | 60s | 1 day | 15 min |
| `FollowUpWorkflow` | 2 | 300s | 30 days | 120 min |

Retry caps are hard limits. `ApprovalWorkflow` intentionally has 1 attempt — approval is a one-shot decision, not a retryable operation.

Non-retryable errors must be explicitly listed in the registry. These errors cause immediate workflow failure without retry.

---

## Stale Workflow Cleanup and Sweep Policy

`computer workflow sweep` identifies workflows exceeding their `stale_after_days` policy and either cancels or archives them.

**Sweep actions:**
- `cancel`: Sends a cancellation signal; workflow completes its current activity then exits cleanly
- `archive`: Marks the workflow as archived in the tracking store; does not interrupt execution (use for informational workflows that have simply outlived their usefulness)

Sweep runs:
1. Daily via a scheduled task (or manually via `computer workflow sweep`)
2. On service restart (checks all running workflows against current sweep policies)

A swept workflow is logged as a `DisturbanceRecord` with `disturbance_type="workflow_sweep"`.

---

## Worker Versioning for Zero-Downtime Upgrades

When a workflow class schema or behavior changes:

1. **Create a new task queue version**: `workflow-runtime-v2` alongside existing `workflow-runtime`
2. **Deploy new workers** on the v2 task queue; old workers continue on the v1 queue
3. **Drain old queue**: new workflows start on v2; existing workflows complete on v1
4. **Monitor** via `computer workflow list` until v1 queue is empty
5. **Decommission** v1 workers after drain is complete

For additive changes (new optional fields only), in-flight migration notes in the registry describe how existing workflows handle the absence of the new field. No drain required for purely additive changes.

For breaking changes (field type change, required field added, behavior change): drain is required.

---

## `FollowUpWorkflow` — Escalation Pattern

The `FollowUpWorkflow` escalation pattern requires careful sequencing:

```python
# Correct: create workflow when loop is created
workflow_id = deterministic_workflow_id("FollowUpWorkflow", loop_id, "initial")

# In loops.resolve tool handler:
# If loop resolved: send "resolved" signal → workflow closes cleanly
# If loop approaching deadline: workflow escalates autonomously to INTERRUPT

# Escalation sequence:
# 1. Workflow reaches follow_up_at: sends reminder signal to attention-engine
# 2. If not resolved by escalation_deadline: workflow sends INTERRUPT signal
# 3. If escalation_action="ABANDON": workflow triggers abandonment policy
```

`FollowUpWorkflow` must be idempotent on the `resolved` signal — receiving it twice (e.g., from a duplicate network call) must not cause double-close.

---

## `ApprovalWorkflow` — Update Handler Pattern

Approvals use Temporal's update handler for atomic accept/deny semantics:

```python
@workflow.update
async def process_approval(self, decision: ApprovalDecision) -> ApprovalResult:
    """
    Update handler: called by identity-service after passkey re-auth verifies
    the approver. The update is atomic — either accepted fully or rejected with
    a typed error. No partial approval states.
    """
    if self.status != "PENDING":
        raise ApprovalAlreadyResolved(self.approval_id)
    self.status = decision.decision  # "APPROVED" or "DENIED"
    return ApprovalResult(approval_id=self.approval_id, decision=decision.decision,
                          decided_by=decision.approver_id, decided_at=decision.timestamp)
```

Stale approvals (> 7d without decision) are cancelled by sweep. Cancelled approvals are logged as `EXPIRED` in the audit trail.

---

## `RoutineWorkflow` — Idempotent Step Execution

Routine steps must be idempotent — the same step executed twice must not cause double-effects:

```python
# Use Temporal's activity idempotency key:
result = await workflow.execute_activity(
    execute_routine_step,
    args=[step],
    start_to_close_timeout=timedelta(minutes=30),
    retry_policy=RetryPolicy(
        maximum_attempts=3,
        backoff_coefficient=2.0,
        non_retryable_error_types=["InvalidStep"],
    ),
    # Idempotency key: step_id ensures activity is not replayed after success
    activity_id=f"{self.routine_id}/{step.step_id}",
)
```

Skip-step recovery: if `skip_on_error=True` and a step fails all retries, the routine logs the failure, marks the step as SKIPPED, and continues to the next step.
