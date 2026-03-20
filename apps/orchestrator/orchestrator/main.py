"""
Orchestrator FastAPI application entry point.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware

from .models import (
    ApprovalEvent,
    HealthResponse,
    Job,
    JobApprovalRequest,
    JobState,
    JobSubmitRequest,
)
from .policy import evaluate_approval_mode
from .state_machine import PolicyViolationError, StateMachine

logger = structlog.get_logger(__name__)

# In-memory job store for development; replace with Postgres in production
_jobs: dict[str, Job] = {}
_state_machine = StateMachine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("orchestrator_starting")
    # TODO: Connect to Postgres, Redis, MQTT broker
    yield
    logger.info("orchestrator_stopping")


app = FastAPI(
    title="Computer Orchestrator",
    description="Job engine, policy evaluation, state machine, and audit kernel",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # ops-web dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health():
    """Health check — polled by bootstrap and glue layer."""
    return HealthResponse(
        status="ok",
        dependencies={
            "postgres": "ok",  # TODO: real DB health check
            "redis": "ok",
            "mqtt": "ok",
        },
    )


@app.get("/ready", tags=["health"])
async def ready():
    """Readiness probe — returns 200 when ready to serve traffic."""
    return {"ready": True}


# ── Jobs ────────────────────────────────────────────────────────────────────

@app.post("/jobs", response_model=Job, status_code=201, tags=["jobs"])
async def submit_job(
    request: JobSubmitRequest,
    x_request_id: str | None = Header(default=None),
    x_operator_id: str | None = Header(default=None),
):
    """
    Submit a new job. Called by control-api (which validates auth first).
    Derives approval_mode from origin × risk_class.
    Transitions to VALIDATING immediately.
    """
    approval_mode = evaluate_approval_mode(request.origin, request.risk_class)
    job = Job(
        type=request.type,
        requested_by=request.requested_by,
        origin=request.origin,
        target_asset_ids=request.target_asset_ids,
        target_capability=request.target_capability,
        target_zone=request.target_zone,
        parameters=request.parameters,
        risk_class=request.risk_class,
        approval_mode=approval_mode,
        request_id=x_request_id,
        timeout_seconds=request.timeout_seconds,
    )

    try:
        job = _state_machine.transition(job, JobState.VALIDATING)
        passed, reason = _state_machine.validate(job)
        if not passed:
            job = _state_machine.transition(job, JobState.REJECTED, reason=reason)
            _jobs[job.job_id] = job
            return job
    except PolicyViolationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Auto-approve if policy permits
    if approval_mode.value in ("NONE", "AUTO", "AUTO_WITH_AUDIT"):
        if approval_mode.value in ("AUTO", "AUTO_WITH_AUDIT"):
            job.approval_event = ApprovalEvent(approved_by="policy")
        job = _state_machine.transition(job, JobState.APPROVED)
        logger.info("job_auto_approved", job_id=job.job_id, approval_mode=approval_mode)

    _jobs[job.job_id] = job
    logger.info("job_submitted", job_id=job.job_id, type=job.type, state=job.state)
    return job


@app.get("/jobs", response_model=list[Job], tags=["jobs"])
async def list_jobs(
    state: str | None = None,
    origin: str | None = None,
    limit: int = 50,
):
    """List jobs with optional filters."""
    jobs = list(_jobs.values())
    if state:
        jobs = [j for j in jobs if j.state.value == state]
    if origin:
        jobs = [j for j in jobs if j.origin.value == origin]
    return sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]


@app.get("/jobs/{job_id}", response_model=Job, tags=["jobs"])
async def get_job(job_id: str):
    """Get a specific job by ID."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.post("/jobs/{job_id}/approve", response_model=Job, tags=["jobs"])
async def approve_job(
    job_id: str,
    approval: JobApprovalRequest,
    x_operator_id: str | None = Header(default=None),
):
    """
    Operator approves a pending job.
    Required for OPERATOR_REQUIRED and OPERATOR_CONFIRM_TWICE approval modes.
    """
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]

    if job.state not in (JobState.VALIDATING, JobState.APPROVED):
        raise HTTPException(
            status_code=409,
            detail=f"Job is in state {job.state}; cannot approve",
        )

    approval_event = ApprovalEvent(
        approved_by=approval.approved_by,
        approval_note=approval.approval_note,
    )
    try:
        job = _state_machine.approve(job, approval_event)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    _jobs[job_id] = job
    return job


@app.post("/jobs/{job_id}/abort", response_model=Job, tags=["jobs"])
async def abort_job(
    job_id: str,
    reason: str = "Operator abort",
    x_operator_id: str | None = Header(default=None),
):
    """Abort a job. Valid from any non-terminal state."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _jobs[job_id]
    job = _state_machine.abort(job, reason)
    _jobs[job_id] = job
    logger.info("job_aborted", job_id=job_id, reason=reason)
    return job


# ── Emergency ───────────────────────────────────────────────────────────────

@app.post("/e-stop", tags=["emergency"])
async def e_stop_all(
    reason: str = "Emergency E-stop",
    x_operator_id: str | None = Header(default=None),
):
    """
    Emergency stop — aborts all EXECUTING jobs immediately.
    FOUNDER_ADMIN only (enforced by control-api auth layer).
    """
    affected = []
    for job_id, job in _jobs.items():
        if job.state == JobState.EXECUTING:
            _jobs[job_id] = _state_machine.abort(job, f"E-STOP: {reason}")
            affected.append(job_id)
    logger.warning("e_stop_all", reason=reason, affected_jobs=len(affected))
    return {"aborted_jobs": affected, "reason": reason}
