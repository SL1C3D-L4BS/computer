# Durable Workflow Strategy

**Status:** Authoritative  
**Owner:** Platform  
**ADR:** ADR-017 (Durable Workflow Plane), ADR-027 (All long-lived tasks use workflow-runtime)  
**Implementation:** `services/workflow-runtime/`  
**Boundary:** `docs/architecture/workflow-orchestrator-boundary.md`

---

## Core Constraint

**No multi-step execution may exist outside `workflow-runtime`.**

Any task that spans more than one user interaction, more than one service call, or more than 30 seconds of wall-clock time is a durable workflow. There are no exceptions.

This constraint prevents the accumulation of "implicit workflows" — sequences of HTTP calls, database state machines, or cron jobs that approximate workflow behavior without the fault-tolerance guarantees.

---

## Temporal as Backbone

Temporal (Python SDK) is the durable execution backbone.

Why Temporal:
- Survives server restarts, crashes, network partitions
- No polling loops, no cron jobs for long-running sequences
- Signal/update pattern for external approval (operator approval gates)
- `asyncio.sleep()` becomes a durable timer (not a real sleep)
- Event sourcing via workflow history enables replay for debugging

### Environment Setup

| Environment | Temporal Server | State Backend |
|-------------|----------------|---------------|
| Development | `temporal server start-dev` | SQLite (local) |
| Production | Temporal Cloud or self-hosted | PostgreSQL |

---

## Core Primitives

### Workflow Definition

```python
from temporalio import workflow, activity
from temporalio.common import RetryPolicy
from datetime import timedelta

@workflow.defn
class HouseholdRoutineWorkflow:
    def __init__(self):
        self._approval_result: dict | None = None
        self._status = "running"

    @workflow.run
    async def run(self, params: dict) -> str:
        # @workflow.init is NOT needed here; use __init__ for pre-signal-race safety
        
        # Step 1: Submit job to orchestrator (via activity — all I/O in activities)
        job_id = await workflow.execute_activity(
            submit_orchestrator_job,
            params,
            task_queue="computer-main",
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
        
        # Step 2: Durable timer — wait for daily check
        await asyncio.sleep(86400)  # This is a Temporal durable timer, not a real sleep
        
        return job_id

    @workflow.signal
    async def job_approved(self, job_id: str) -> None:
        """Fire-and-forget signal from orchestrator (approval notification)."""
        self._approval_result = {"status": "approved", "job_id": job_id}

    @workflow.signal
    async def job_failed(self, reason: str) -> None:
        """Fire-and-forget signal from orchestrator (failure notification)."""
        self._approval_result = {"status": "failed", "reason": reason}

    @workflow.update
    async def get_status(self) -> dict:
        """Request/response update — use for acknowledgment patterns."""
        return {"status": self._status, "approval": self._approval_result}

    @workflow.query
    def current_state(self) -> str:
        """Sync read-only query — use for polling."""
        return self._status
```

### Activity Definition

```python
@activity.defn
async def submit_orchestrator_job(params: dict) -> str:
    """All I/O (HTTP calls, DB writes) MUST be in activities, not workflows."""
    async with httpx.AsyncClient() as client:
        r = await client.post("http://control-api:8000/jobs", json=params)
        return r.json()["id"]
```

### Signal vs Update vs Query

| Pattern | Use case | Temporal primitive |
|---------|----------|-------------------|
| Notify workflow of external event | Job approved, alarm triggered | `@workflow.signal` (fire-and-forget) |
| Request workflow response | Acknowledge approval, get current plan | `@workflow.update` (request/response) |
| Read workflow state without side effects | Polling status from UI | `@workflow.query` (sync read-only) |

---

## Use Cases

| Use Case | Workflow Type | Duration |
|----------|--------------|---------|
| Multi-day irrigation schedule | `IrrigationScheduleWorkflow` | Days |
| Household morning routine | `MorningRoutineWorkflow` | ~1 hour |
| Operator approval gate | `ApprovalGateWorkflow` | Minutes–hours |
| Greenhouse climate cycle | `ClimateControlWorkflow` | Ongoing |
| Robot mission with waypoints | `RoverMissionWorkflow` | Hours |

---

## Retry Policy

Default retry policy for activities:

```python
RetryPolicy(
    maximum_attempts=5,
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    non_retryable_error_types=["AuthorizationDeniedError", "InvalidJobStateError"],
)
```

Non-retryable errors: authorization failures, invalid state transitions.  
Retryable: network errors, timeouts, transient service unavailability.

---

## Worker Versioning

Temporal supports zero-downtime deploys via task queue versioning:

```python
# New worker version
await client.update_worker_build_id_compatibility(
    task_queue="computer-main",
    build_id="v1.2.0",
    new_default=True,
)
```

Long-running workflows continue on the old version until they complete.

---

## Boundary With Orchestrator

See `docs/architecture/workflow-orchestrator-boundary.md` for the full contract.

**Critical constraint:** `workflow-runtime` MUST NOT publish to MQTT directly.  
MQTT is the hardware command bus. Only the `orchestrator` publishes to MQTT.

Correct cross-boundary sequence:
1. `workflow-runtime` calls `control-api POST /jobs` (creates an orchestrator job)
2. `orchestrator` approves and executes via MQTT
3. `orchestrator` signals `workflow-runtime` via Temporal signal (`job_completed`)
4. `workflow-runtime` resumes the workflow

---

## `@workflow.init` Pattern

To prevent signal races (signals arriving before `run` executes):

```python
@workflow.defn
class SafeWorkflow:
    @workflow.init
    def __init__(self, initial_params: dict) -> None:
        # Receives the same args as run(); safe to initialize state here
        self._params = initial_params
        self._signals_received = []

    @workflow.run
    async def run(self, initial_params: dict) -> str:
        # State is already initialized; no race window
        ...
```

Use `@workflow.init` for any workflow that accepts signals immediately after starting.
