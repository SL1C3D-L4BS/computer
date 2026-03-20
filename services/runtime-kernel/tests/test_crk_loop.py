"""
CRK Loop Unit Tests — the 5 operational invariants.

These tests run against the runtime-kernel stub skeleton (no real services needed).
They prove the CRK loop is correct before Phase 0B begins.

Reference: docs/architecture/runtime-kernel.md (Phase 0A gate section)
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient, ASGITransport

CONTRACTS_PATH = Path(__file__).parent.parent.parent.parent / "packages" / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

from models import (
    Mode, Surface, RiskClass, Origin, MemoryScope,
    WorkflowBindingType,
)

# Import app — adjust to service root
sys.path.insert(0, str(Path(__file__).parent.parent))
from runtime_kernel.main import app, _mode_map
from runtime_kernel.loop import get_audit_log, _audit_log


@pytest.fixture(autouse=True)
def clear_state():
    """Reset shared state between tests."""
    _mode_map.clear()
    _audit_log.clear()
    yield
    _mode_map.clear()
    _audit_log.clear()


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c


# ─────────────────────────────────────────────────────────────────────────────
# Invariant 1: trace_id continuity
# ─────────────────────────────────────────────────────────────────────────────

class TestTraceIdContinuity:
    """trace_id in InputEnvelope must appear in ResponseEnvelope and all step logs."""

    async def test_trace_id_preserved_in_response(self, client):
        trace_id = f"test-trace-{uuid.uuid4().hex[:8]}"
        r = await client.post("/execute", json={
            "raw_input": "What is the weather?",
            "surface": "CHAT",
            "user_id": "user_001",
            "session_id": "sess_001",
            "trace_id": trace_id,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["trace_id"] == trace_id, \
            f"trace_id mismatch: sent {trace_id!r}, got {body['trace_id']!r}"

    async def test_trace_id_in_audit_records(self, client):
        trace_id = f"audit-trace-{uuid.uuid4().hex[:8]}"
        await client.post("/execute", json={
            "raw_input": "Tell me a joke",
            "surface": "VOICE",
            "user_id": "user_001",
            "session_id": "sess_001",
            "trace_id": trace_id,
        })
        audit_r = await client.get(f"/audit/{trace_id}")
        assert audit_r.status_code == 200
        steps = audit_r.json()
        assert len(steps) >= 5, f"Expected at least 5 audit steps, got {len(steps)}"
        step_names = [s["step"] for s in steps]
        assert "1_input_ingestion" in step_names
        assert "6_authz_check" in step_names
        assert "9_attention_decision" in step_names
        assert "10_response_render" in step_names

    async def test_auto_generated_trace_id_is_consistent(self, client):
        """If no trace_id provided, one must be generated and used consistently."""
        r = await client.post("/execute", json={
            "raw_input": "Hello",
            "surface": "CHAT",
            "user_id": "user_001",
            "session_id": "sess_001",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["trace_id"], "trace_id must be auto-generated"
        # Verify audit records use the same auto-generated trace_id
        audit_r = await client.get(f"/audit/{body['trace_id']}")
        assert audit_r.status_code == 200
        steps = audit_r.json()
        assert len(steps) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Invariant 2: mode continuity
# ─────────────────────────────────────────────────────────────────────────────

class TestModeContinuity:
    """Mode must be preserved per {user_id × surface} or changed with an audit reason."""

    async def test_ops_surface_defaults_to_site_mode(self, client):
        r = await client.post("/execute", json={
            "raw_input": "Show me job status",
            "surface": "OPS",
            "user_id": "operator_001",
            "session_id": "sess_ops",
        })
        assert r.status_code == 200
        # OPS surface → SITE mode default
        state_r = await client.get("/state")
        state = state_r.json()
        key = "operator_001:OPS"
        assert key in state["mode_by_surface"], f"Mode map missing key {key}"
        assert state["mode_by_surface"][key] == "SITE"

    async def test_voice_surface_defaults_to_personal_mode(self, client):
        r = await client.post("/execute", json={
            "raw_input": "What time is it?",
            "surface": "VOICE",
            "user_id": "founder_001",
            "session_id": "sess_v",
        })
        assert r.status_code == 200
        state_r = await client.get("/state")
        state = state_r.json()
        key = "founder_001:VOICE"
        assert state["mode_by_surface"].get(key) == "PERSONAL"

    async def test_same_user_different_surface_different_mode(self, client):
        """Founder on OPS = SITE; same founder on VOICE = PERSONAL. No bleed."""
        await client.post("/execute", json={
            "raw_input": "Run site diagnostics",
            "surface": "OPS",
            "user_id": "founder_001",
            "session_id": "sess_ops",
        })
        await client.post("/execute", json={
            "raw_input": "What's for dinner?",
            "surface": "VOICE",
            "user_id": "founder_001",
            "session_id": "sess_v",
        })
        state_r = await client.get("/state")
        state = state_r.json()
        assert state["mode_by_surface"]["founder_001:OPS"] == "SITE"
        assert state["mode_by_surface"]["founder_001:VOICE"] == "PERSONAL"


# ─────────────────────────────────────────────────────────────────────────────
# Invariant 3: HIGH-risk request → 7b (orchestrator), NOT 7a
# ─────────────────────────────────────────────────────────────────────────────

class TestHighRiskGoesTo7b:
    """HIGH-risk control requests create orchestrator jobs (7b), never tools (7a)."""

    async def test_irrigation_actuation_creates_job(self, client):
        trace_id = f"high-risk-{uuid.uuid4().hex[:8]}"
        r = await client.post("/execute", json={
            "raw_input": "Open irrigation valve for zone 1",
            "surface": "OPS",
            "user_id": "operator_001",
            "session_id": "sess_ops",
            "trace_id": trace_id,
        })
        assert r.status_code == 200
        body = r.json()
        # 7b must produce proposed_jobs
        assert len(body["proposed_jobs"]) > 0, \
            "HIGH-risk request must produce proposed_jobs (7b path)"

    async def test_high_risk_audit_shows_7b_not_7a(self, client):
        trace_id = f"7b-audit-{uuid.uuid4().hex[:8]}"
        await client.post("/execute", json={
            "raw_input": "Enable greenhouse heater",
            "surface": "OPS",
            "user_id": "operator_001",
            "session_id": "sess_ops",
            "trace_id": trace_id,
        })
        audit_r = await client.get(f"/audit/{trace_id}")
        steps = {s["step"]: s for s in audit_r.json()}
        # 7b must be "ok" or "stub"
        assert "7b_control_job_bind" in steps
        assert steps["7b_control_job_bind"]["status"] in ("ok", "stub")
        # 7a must be "noop" (skipped for HIGH-risk)
        assert "7a_tool_invocation" in steps
        assert steps["7a_tool_invocation"]["status"] == "noop", \
            "7a must be noop for HIGH-risk request"

    async def test_high_risk_response_contains_job_id(self, client):
        r = await client.post("/execute", json={
            "raw_input": "Arm field rover for mission",
            "surface": "OPS",
            "user_id": "operator_001",
            "session_id": "sess",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["proposed_jobs"], "Must return job IDs for rover mission request"
        assert all(body["proposed_jobs"]), "Job IDs must be non-empty strings"


# ─────────────────────────────────────────────────────────────────────────────
# Invariant 4: LOW-risk personal request stays in assistant plane
# ─────────────────────────────────────────────────────────────────────────────

class TestLowRiskStaysInAssistantPlane:
    """LOW-risk personal requests must NOT create orchestrator jobs (7b no-op)."""

    async def test_informational_query_no_jobs(self, client):
        trace_id = f"low-risk-{uuid.uuid4().hex[:8]}"
        r = await client.post("/execute", json={
            "raw_input": "What is the weather today?",
            "surface": "CHAT",
            "user_id": "user_001",
            "session_id": "sess",
            "trace_id": trace_id,
        })
        assert r.status_code == 200
        body = r.json()
        assert len(body["proposed_jobs"]) == 0, \
            f"LOW-risk informational query must not create jobs, got: {body['proposed_jobs']}"

    async def test_low_risk_audit_shows_7b_noop(self, client):
        trace_id = f"7b-noop-{uuid.uuid4().hex[:8]}"
        await client.post("/execute", json={
            "raw_input": "Tell me about the greenhouse crops",
            "surface": "VOICE",
            "user_id": "founder_001",
            "session_id": "sess",
            "trace_id": trace_id,
        })
        audit_r = await client.get(f"/audit/{trace_id}")
        steps = {s["step"]: s for s in audit_r.json()}
        assert "7b_control_job_bind" in steps
        assert steps["7b_control_job_bind"]["status"] == "noop", \
            "7b must be noop for LOW-risk request"

    async def test_low_risk_7a_attempted(self, client):
        """LOW-risk requests attempt 7a (tool), not 7b."""
        trace_id = f"7a-ok-{uuid.uuid4().hex[:8]}"
        await client.post("/execute", json={
            "raw_input": "What time does the sun set?",
            "surface": "CHAT",
            "user_id": "user_001",
            "session_id": "sess",
            "trace_id": trace_id,
        })
        audit_r = await client.get(f"/audit/{trace_id}")
        steps = {s["step"]: s for s in audit_r.json()}
        assert "7a_tool_invocation" in steps
        assert steps["7a_tool_invocation"]["status"] in ("ok", "stub"), \
            "7a must be attempted (ok or stub) for LOW-risk request"


# ─────────────────────────────────────────────────────────────────────────────
# Invariant 5: Workflow-bound request returns durable workflow_id
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkflowBinding:
    """Workflow-bound requests must return a non-null workflow_id."""

    async def test_schedule_request_returns_workflow_binding(self, client):
        r = await client.post("/execute", json={
            "raw_input": "Remind me to check the greenhouse tomorrow morning",
            "surface": "VOICE",
            "user_id": "founder_001",
            "session_id": "sess",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["workflow_binding"] is not None, \
            "Schedule request must return workflow_binding"
        assert body["workflow_binding"]["workflow_id"], \
            "workflow_id must be non-null"

    async def test_durable_workflow_has_task_queue(self, client):
        r = await client.post("/execute", json={
            "raw_input": "Schedule irrigation for next week",
            "surface": "OPS",
            "user_id": "operator_001",
            "session_id": "sess",
        })
        assert r.status_code == 200
        body = r.json()
        wb = body.get("workflow_binding")
        if wb and wb.get("type") == "DURABLE":
            assert wb.get("temporal_task_queue"), \
                "DURABLE workflow must have temporal_task_queue"

    async def test_simple_query_has_immediate_or_null_binding(self, client):
        """Simple queries should not produce DURABLE workflow bindings."""
        r = await client.post("/execute", json={
            "raw_input": "What is the current temperature?",
            "surface": "VOICE",
            "user_id": "user_001",
            "session_id": "sess",
        })
        assert r.status_code == 200
        body = r.json()
        wb = body.get("workflow_binding")
        if wb:
            assert wb["type"] == "IMMEDIATE", \
                "Simple query should use IMMEDIATE binding if any"


# ─────────────────────────────────────────────────────────────────────────────
# Health and interrupt endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestHealthAndInterrupt:
    async def test_health(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    async def test_interrupt_endpoint(self, client):
        r = await client.post("/interrupt", json={
            "user_id": "operator_001",
            "reason": "E-stop pressed",
            "surface": "EVENT",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["trace_id"], "Interrupt must return trace_id"

    async def test_state_endpoint(self, client):
        r = await client.get("/state")
        assert r.status_code == 200
        state = r.json()
        assert "mode_by_surface" in state
        assert "active_workflow_ids" in state
        assert "attention_load" in state
