"""
Workflow Runtime — Durable execution via Temporal

Owns: Long-lived workflow state, durable timers, signal/update handlers.
Does NOT own: Job state machine (that is orchestrator), hardware actuation.

ADR: ADR-017 (Durable Workflow Plane), ADR-031 (WR ↔ ORC boundary)
Reference: docs/architecture/durable-workflow-strategy.md
           docs/architecture/workflow-orchestrator-boundary.md

Authority:
  Owns: Temporal lifecycle, task queues, workflow execution
  Does NOT own: Orchestrator job transitions, MQTT publish, hardware

TEMPORAL TASK QUEUE: computer-main
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import structlog

CONTRACTS_PATH = Path(__file__).parent.parent.parent.parent / "packages" / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

log = structlog.get_logger(__name__)

TASK_QUEUE = "computer-main"

app = FastAPI(
    title="Workflow Runtime",
    description="Durable workflow execution via Temporal — step 5 backend",
    version="0.1.0",
)

# ── In-memory stub state (replace with real Temporal client in v1) ────────────
_workflows: dict[str, dict[str, Any]] = {}


class StartWorkflowRequest(BaseModel):
    workflow_type: str         # e.g. "HouseholdRoutineWorkflow"
    workflow_id: str | None = None
    args: dict[str, Any] = {}
    task_queue: str = TASK_QUEUE


class WorkflowSignalRequest(BaseModel):
    workflow_id: str
    signal_name: str
    payload: dict[str, Any] = {}


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "workflow-runtime", "task_queue": TASK_QUEUE}


@app.post("/workflows/start")
async def start_workflow(req: StartWorkflowRequest) -> dict[str, Any]:
    """
    Start a durable Temporal workflow.
    Stub: stores in-memory; real version uses temporalio client.

    Authority:
    - MAY create orchestrator jobs (via control-api)
    - MAY query job state
    - MUST NOT directly actuate hardware (MQTT)
    - MUST NOT modify orchestrator job state directly
    """
    workflow_id = req.workflow_id or f"wf-{req.workflow_type}-{uuid.uuid4().hex[:8]}"
    _workflows[workflow_id] = {
        "workflow_id": workflow_id,
        "type": req.workflow_type,
        "status": "RUNNING",
        "task_queue": req.task_queue,
        "args": req.args,
        "pending_signals": [],
    }
    log.info("workflow_runtime.started", workflow_id=workflow_id, type=req.workflow_type)
    return {
        "workflow_id": workflow_id,
        "status": "RUNNING",
        "task_queue": req.task_queue,
    }


@app.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict[str, Any]:
    """Query workflow state. Read-only."""
    wf = _workflows.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    return wf


@app.post("/workflows/{workflow_id}/signal")
async def signal_workflow(workflow_id: str, req: WorkflowSignalRequest) -> dict[str, str]:
    """
    Send a signal to a running workflow (fire-and-forget).
    Used by orchestrator to send job_approved / job_failed notifications.
    """
    wf = _workflows.get(workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
    wf["pending_signals"].append({"signal": req.signal_name, "payload": req.payload})
    log.info("workflow_runtime.signal", workflow_id=workflow_id, signal=req.signal_name)
    return {"status": "signal_accepted", "workflow_id": workflow_id}


@app.get("/workflows")
async def list_workflows() -> dict[str, Any]:
    """List all active workflow IDs."""
    return {
        "workflows": [
            {"workflow_id": wid, "type": wf["type"], "status": wf["status"]}
            for wid, wf in _workflows.items()
        ],
        "count": len(_workflows),
    }


# ── Stub Workflow Definitions (real versions use @workflow.defn decorator) ────

class HouseholdRoutineWorkflow:
    """
    Reference workflow — Temporal SDK version.
    
    In production with temporalio SDK:
    
    @workflow.defn
    class HouseholdRoutineWorkflow:
        def __init__(self):
            self._job_result = None
            
        @workflow.run
        async def run(self, params: dict) -> str:
            # Activity: submit job to orchestrator
            job_id = await workflow.execute_activity(
                create_orchestrator_job,
                params,
                task_queue="computer-main",
                start_to_close_timeout=timedelta(minutes=5),
            )
            # Durable timer — survives restarts
            await asyncio.sleep(3600)  # Wait 1 hour
            return job_id
            
        @workflow.signal
        async def job_approved(self, job_id: str) -> None:
            self._job_result = {"status": "approved", "job_id": job_id}
            
        @workflow.update
        async def get_status(self) -> dict:
            return {"job_result": self._job_result}
    
    Constraint: MUST NOT publish to MQTT directly.
    Constraint: MUST NOT modify orchestrator job state directly.
    """
    pass
