# Workflow Registry Model

**Status:** Active  
**Version:** 1.0.0  
**Owner:** Workflow-runtime maintainer

---

## Overview

Every workflow class in `workflow-runtime` must be registered with a structured record. The registry prevents sprawl by making every workflow's contract, timeout behavior, and migration story explicit before it can be deployed.

**Hard rule:** A new workflow class requires both an ADR and a registry entry. No exceptions.

---

## Registry Schema

Every workflow class must provide all fields:

| Field | Type | Description |
| --- | --- | --- |
| `name` | `str` | Canonical class name (matches Python class name exactly) |
| `version` | `str` | Semver (e.g., `1.0.0`); bump on any schema or behavior change |
| `domain` | `str` | Owning domain: `household` / `founder` / `site` |
| `description` | `str` | One-sentence purpose statement |
| `input_schema` | `dict` | Named fields, types, required/optional |
| `timeout_policy` | `dict` | `max_run_duration_days`, `heartbeat_interval_minutes` |
| `retry_policy` | `dict` | `max_attempts`, `backoff_seconds`, `non_retryable_errors: list[str]` |
| `sweep_policy` | `dict` | `stale_after_days`, `sweep_action: "cancel"\|"archive"` |
| `migration_notes` | `str` | How in-flight workflows survive a class version update |

---

## Canonical Workflow Registry

V4 defines exactly 4 canonical workflow classes. No new patterns without ADR.

### ReminderWorkflow

```json
{
  "name": "ReminderWorkflow",
  "version": "1.0.0",
  "domain": "household",
  "description": "Durable timer with pause/resume; fires reminder signal and marks CLOSED on acknowledgment.",
  "input_schema": {
    "reminder_id": {"type": "str", "required": true},
    "user_id":     {"type": "str", "required": true},
    "message":     {"type": "str", "required": true},
    "fire_at":     {"type": "iso8601", "required": true},
    "recurrence":  {"type": "str", "required": false, "values": ["daily", "weekly", "none"]},
    "max_age_days": {"type": "int", "required": false, "default": 30}
  },
  "timeout_policy": {
    "max_run_duration_days": 90,
    "heartbeat_interval_minutes": 60
  },
  "retry_policy": {
    "max_attempts": 3,
    "backoff_seconds": 30,
    "non_retryable_errors": ["ReminderNotFound", "UserNotFound"]
  },
  "sweep_policy": {
    "stale_after_days": 90,
    "sweep_action": "cancel"
  },
  "migration_notes": "V1→V2: adding recurrence field. In-flight workflows without recurrence field will use default=none; no replay required."
}
```

---

### ApprovalWorkflow

```json
{
  "name": "ApprovalWorkflow",
  "version": "1.0.0",
  "domain": "household",
  "description": "Waits for explicit approval or denial via Temporal update handler; stale after 7d.",
  "input_schema": {
    "approval_id":   {"type": "str", "required": true},
    "requester_id":  {"type": "str", "required": true},
    "approver_ids":  {"type": "list[str]", "required": true},
    "description":   {"type": "str", "required": true},
    "expires_at":    {"type": "iso8601", "required": true},
    "risk_class":    {"type": "str", "required": true, "values": ["LOW", "MEDIUM", "HIGH"]},
    "requires_passkey": {"type": "bool", "required": false, "default": false}
  },
  "timeout_policy": {
    "max_run_duration_days": 7,
    "heartbeat_interval_minutes": 30
  },
  "retry_policy": {
    "max_attempts": 1,
    "backoff_seconds": 0,
    "non_retryable_errors": ["ApprovalExpired", "ApproverNotFound"]
  },
  "sweep_policy": {
    "stale_after_days": 7,
    "sweep_action": "cancel"
  },
  "migration_notes": "V1→V2: adding requires_passkey field. In-flight workflows use default=false (no passkey required); new approvals pick up new field."
}
```

---

### RoutineWorkflow

```json
{
  "name": "RoutineWorkflow",
  "version": "1.0.0",
  "domain": "household",
  "description": "Daily schedule execution with skip-step recovery and idempotent retries.",
  "input_schema": {
    "routine_id":    {"type": "str", "required": true},
    "schedule":      {"type": "cron_expr", "required": true},
    "steps":         {"type": "list[dict]", "required": true},
    "skip_on_error": {"type": "bool", "required": false, "default": false}
  },
  "timeout_policy": {
    "max_run_duration_days": 1,
    "heartbeat_interval_minutes": 15
  },
  "retry_policy": {
    "max_attempts": 3,
    "backoff_seconds": 60,
    "non_retryable_errors": ["RoutineNotFound", "InvalidStep"]
  },
  "sweep_policy": {
    "stale_after_days": 2,
    "sweep_action": "archive"
  },
  "migration_notes": "Step schema changes require explicit version bump and in-flight workflow drain before deploying new worker."
}
```

---

### FollowUpWorkflow

```json
{
  "name": "FollowUpWorkflow",
  "version": "1.0.0",
  "domain": "founder",
  "description": "Signal-triggered from loops.resolve; escalates to INTERRUPT after deadline if unresolved.",
  "input_schema": {
    "loop_id":      {"type": "str", "required": true},
    "user_id":      {"type": "str", "required": true},
    "description":  {"type": "str", "required": true},
    "follow_up_at": {"type": "iso8601", "required": true},
    "escalation_deadline": {"type": "iso8601", "required": false},
    "escalation_action":   {"type": "str", "required": false, "values": ["INTERRUPT", "ABANDON"]}
  },
  "timeout_policy": {
    "max_run_duration_days": 30,
    "heartbeat_interval_minutes": 120
  },
  "retry_policy": {
    "max_attempts": 2,
    "backoff_seconds": 300,
    "non_retryable_errors": ["LoopNotFound", "LoopAlreadyClosed"]
  },
  "sweep_policy": {
    "stale_after_days": 30,
    "sweep_action": "cancel"
  },
  "migration_notes": "Adding escalation fields is backward-compatible; in-flight workflows without these fields use default behavior (no escalation)."
}
```

---

## Adding a New Workflow Class

1. Write an ADR explaining why the 4 canonical classes are insufficient
2. Add a registry entry to this document with all fields filled
3. Implement the class in `workflow-runtime/workflows.py`
4. Add at least one eval fixture in `eval-fixtures`
5. Add a rubric check for the new class
6. Update `computer workflow list` to include the new class

See also: `docs/architecture/workflow-production-patterns.md`
