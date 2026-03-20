# Workflow-Runtime ↔ Orchestrator Boundary

**Status:** Authoritative  
**Owner:** Platform  
**ADR:** ADR-031  
**Enforcement:** Violation of any NEVER rule is a P0 architectural bug. Revert immediately.

---

## Purpose

`workflow-runtime` (Temporal) and `orchestrator` are two separate execution engines with different purposes, different failure semantics, and different state ownership. Without an explicit contract, they will accumulate hidden coupling that produces subtle, hard-to-debug failures.

---

## The Two Engines

| Engine | Technology | Owns | Does NOT own |
|--------|-----------|------|--------------|
| `workflow-runtime` | Temporal (Python SDK) | Long-lived workflow execution, durable timers, signal/update handling | Job state machine, hardware actuation |
| `orchestrator` | FastAPI + PostgreSQL + MQTT | Job state machine, site-control command dispatch, approval management | Temporal lifecycle, workflow execution |

---

## Contract Rules

### Permitted: workflow-runtime → orchestrator

| Rule | Mechanism | Notes |
|------|-----------|-------|
| WR MAY create orchestrator jobs | Via `control-api POST /jobs` or internal job API | workflow-runtime submits a job as `origin=SYSTEM` or `origin=SCHEDULE` |
| WR MAY query job state | Via `orchestrator GET /jobs/{id}` | Read-only polling; never blocks the workflow (use activity) |
| WR MAY subscribe to job completion signals | Via Temporal signal from ORC callback | See ORC→WR below |

### Permitted: orchestrator → workflow-runtime

| Rule | Mechanism | Notes |
|------|-----------|-------|
| ORC MAY send signals to workflow-runtime | Via Temporal client `send_signal` | Used for: job approved, job failed, approval timeout |
| ORC MAY query workflow state | Via Temporal client `query` | Used for: checking if a workflow is still active |

### NEVER rules (P0 violations)

| Rule | Why |
|------|-----|
| `workflow-runtime` MUST NOT publish to MQTT directly | MQTT is the hardware command bus; only `orchestrator` can command hardware |
| `workflow-runtime` MUST NOT modify orchestrator job state directly (no DB writes) | Orchestrator owns the job state machine; WR must submit jobs, not mutate them |
| `orchestrator` MUST NOT create or cancel Temporal workflows | Temporal lifecycle is owned by workflow-runtime; ORC emits signals only |
| `orchestrator` MUST NOT manage Temporal task queues | Task queue is an internal workflow-runtime concern |
| Neither MUST call the other's internal database | All interaction is via HTTP API or Temporal signal |

---

## Sequence: Approval-Gated Workflow

The most common cross-boundary flow: a durable workflow waits for operator approval.

```
1. workflow-runtime creates a job via control-api
   InputEnvelope → runtime-kernel → step 7b → orchestrator
   Job enters VALIDATING state

2. orchestrator sends approval request to ops-web / notification

3. Operator approves via control-api PATCH /jobs/{id}/approve
   orchestrator transitions job: VALIDATING → APPROVED

4. orchestrator signals workflow-runtime: job_approved(job_id)
   (Temporal signal via temporal client)

5. workflow-runtime resumes the waiting workflow
   Workflow proceeds to next activity

6. orchestrator transitions job: APPROVED → EXECUTING → COMPLETED
   (orchestrator drives the job state after approval)
```

**The boundary:** step 4 (ORC → signal → WR) and step 5 (WR resumes) are the only coupling point. They communicate via Temporal signal, not shared state.

---

## Sequence: Long-Running Household Task

Example: a multi-day irrigation schedule with daily state updates.

```
workflow-runtime                         orchestrator
      |                                       |
      | -- START HouseholdRoutineWorkflow --> |
      |                                       |
      | -- create_daily_job (Activity) -----> control-api
      |                                       |-- job enters VALIDATING/APPROVED
      |                                       |-- executes via MQTT
      |                                       |-- job reaches COMPLETED
      |                                       |
      | <-- signal: job_completed(job_id) --- |
      |                                       |
      | -- asyncio.sleep(24h timer) --------> | (durable timer, survives restart)
      |                                       |
      | [next day: timer fires, repeat] ----> |
```

**workflow-runtime** manages the schedule loop. **orchestrator** manages each daily job's execution.

---

## Error Handling

| Error | Response |
|-------|----------|
| WR cannot reach `control-api` to create a job | Retry with exponential backoff (Temporal activity retry policy); alert if threshold exceeded |
| ORC job fails (FAILED state) | ORC signals WR with `job_failed(job_id, reason)`; WR decides: retry, escalate, or abort workflow |
| ORC never signals back (timeout) | WR has a durable timeout (`asyncio.sleep`); escalates to `attention-engine` if approval not received |
| WR workflow crashes | Temporal replays from last event; ORC is unaffected |
| ORC crashes | Job state in Postgres persists; WR retries polling when ORC recovers |

---

## Related Documents

- `docs/architecture/runtime-kernel.md`
- `docs/architecture/kernel-authority-model.md`
- `docs/architecture/durable-workflow-strategy.md`
- `docs/adr/ADR-031-workflow-orchestrator-boundary.md`
