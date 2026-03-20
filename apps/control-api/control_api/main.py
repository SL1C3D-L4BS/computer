"""
Control API — the authenticated external surface for Computer.

Rules:
- Accepts requests only; never mutates job state directly
- Validates auth and forwards to orchestrator
- Returns orchestrator responses to callers
- Never publishes to MQTT
- Never calls control services directly
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Header, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
security = HTTPBearer()


class JobSubmitRequest(BaseModel):
    type: str
    target_asset_ids: list[str]
    target_capability: str | None = None
    target_zone: str | None = None
    parameters: dict = {}
    risk_class: str
    origin: str = "OPERATOR"
    timeout_seconds: int = 300


class JobApprovalRequest(BaseModel):
    approved_by: str
    approval_note: str | None = None
    second_confirmation: bool = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("control_api_starting", orchestrator_url=ORCHESTRATOR_URL)
    yield
    logger.info("control_api_stopping")


app = FastAPI(
    title="Computer Control API",
    description="Authenticated external surface for job submission, status queries, and approvals",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_operator_id(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Validate Bearer token and return operator_id.
    Stub: in production, validate JWT and extract sub claim.
    """
    # TODO: validate JWT with identity-service
    return "operator_stub"


def generate_request_id() -> str:
    return str(uuid.uuid4())


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    """Health check — also checks orchestrator connectivity."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{ORCHESTRATOR_URL}/health", timeout=5.0)
            orch_status = resp.json().get("status", "unknown") if resp.status_code == 200 else "down"
    except Exception:
        orch_status = "unreachable"

    return {
        "status": "ok" if orch_status == "ok" else "degraded",
        "service": "control-api",
        "version": "0.1.0",
        "dependencies": {"orchestrator": orch_status},
    }


# ── Jobs ────────────────────────────────────────────────────────────────────

@app.post("/jobs", status_code=201, tags=["jobs"])
async def submit_job(
    request: JobSubmitRequest,
    operator_id: str = Depends(get_operator_id),
):
    """
    Submit a job. Validates auth, generates request_id, forwards to orchestrator.
    This endpoint accepts but never mutates job state.
    """
    request_id = generate_request_id()
    logger.info("job_submit_forwarding", type=request.type, operator=operator_id, request_id=request_id)

    payload = request.model_dump()
    payload["requested_by"] = operator_id

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/jobs",
                json=payload,
                headers={"X-Request-ID": request_id, "X-Operator-ID": operator_id},
                timeout=30.0,
            )
            if resp.status_code not in (200, 201):
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable")


@app.get("/jobs", tags=["jobs"])
async def list_jobs(
    state: str | None = None,
    origin: str | None = None,
    limit: int = 50,
    operator_id: str = Depends(get_operator_id),
):
    """List jobs. Reads from orchestrator."""
    params = {"limit": limit}
    if state:
        params["state"] = state
    if origin:
        params["origin"] = origin
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{ORCHESTRATOR_URL}/jobs", params=params, timeout=10.0)
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable")


@app.get("/jobs/{job_id}", tags=["jobs"])
async def get_job(job_id: str, operator_id: str = Depends(get_operator_id)):
    """Get a specific job. Reads from orchestrator."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{ORCHESTRATOR_URL}/jobs/{job_id}", timeout=10.0)
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable")


@app.post("/jobs/{job_id}/approve", tags=["jobs"])
async def approve_job(
    job_id: str,
    approval: JobApprovalRequest,
    operator_id: str = Depends(get_operator_id),
):
    """Operator approves a pending job."""
    request_id = generate_request_id()
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/jobs/{job_id}/approve",
                json=approval.model_dump(),
                headers={"X-Request-ID": request_id, "X-Operator-ID": operator_id},
                timeout=10.0,
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable")


@app.post("/jobs/{job_id}/abort", tags=["jobs"])
async def abort_job(
    job_id: str,
    reason: str = "Operator abort",
    operator_id: str = Depends(get_operator_id),
):
    """Abort a job."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/jobs/{job_id}/abort",
                params={"reason": reason},
                headers={"X-Operator-ID": operator_id},
                timeout=10.0,
            )
            if resp.status_code == 404:
                raise HTTPException(status_code=404, detail="Job not found")
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable")


@app.post("/e-stop", tags=["emergency"])
async def e_stop(
    reason: str = "Emergency E-stop",
    operator_id: str = Depends(get_operator_id),
):
    """Emergency stop all executing jobs. FOUNDER_ADMIN only."""
    # TODO: verify operator_id has FOUNDER_ADMIN role
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ORCHESTRATOR_URL}/e-stop",
                params={"reason": reason},
                headers={"X-Operator-ID": operator_id},
                timeout=30.0,
            )
            return resp.json()
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Orchestrator unavailable")
