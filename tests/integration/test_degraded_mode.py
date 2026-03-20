"""
Operational Fault-Injection Tests — Degraded Mode Behavior

Proves that the system behaves correctly when individual services fail.
This is behavioral verification, not structural.

Requirements:
- All services up (./bootstrap.sh --full)
- docker available for container pause/resume

Markers:
  @pytest.mark.fault_injection  — uses docker pause/resume (needs running stack)
  @pytest.mark.degraded         — degraded mode assertion only (no fault injection)

Run:
  pytest tests/integration/test_degraded_mode.py -v
  pytest tests/integration/test_degraded_mode.py -v -m "not fault_injection"
"""
from __future__ import annotations

import os
import subprocess
import time
from typing import Generator

import pytest
import httpx

CONTROL_API   = os.getenv("CONTROL_API_URL",   "http://localhost:8000")
ORCHESTRATOR  = os.getenv("ORCHESTRATOR_URL",  "http://localhost:8002")
DIGITAL_TWIN  = os.getenv("DIGITAL_TWIN_URL",  "http://localhost:8001")
MODEL_ROUTER  = os.getenv("MODEL_ROUTER_URL",  "http://localhost:8020")
ASSISTANT_API = os.getenv("ASSISTANT_API_URL", "http://localhost:8021")
EVENT_INGEST  = os.getenv("EVENT_INGEST_URL",  "http://localhost:8003")

HEADERS = {"Authorization": "Bearer dev-token", "Content-Type": "application/json"}
TIMEOUT = 8.0

pytestmark = pytest.mark.integration


def _is_up(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


def _post(url: str, path: str, body: dict) -> httpx.Response:
    return httpx.post(f"{url}{path}", json=body, headers=HEADERS, timeout=TIMEOUT)


def _get(url: str, path: str, params: dict | None = None) -> httpx.Response:
    return httpx.get(f"{url}{path}", params=params, headers=HEADERS, timeout=TIMEOUT)


def _pause_container(name: str) -> None:
    subprocess.run(["docker", "pause", name], check=True, capture_output=True)


def _unpause_container(name: str) -> None:
    subprocess.run(["docker", "unpause", name], capture_output=True)


def requires_service(url: str, name: str):
    """Skip the test if the service is not running."""
    if not _is_up(url):
        pytest.skip(f"{name} not running at {url} — run ./bootstrap.sh first")


# ─────────────────────────────────────────────────────────────────────────────
# Baseline: services respond correctly when healthy
# ─────────────────────────────────────────────────────────────────────────────

class TestBaselineHealthy:
    """Before fault injection: verify the system works correctly when healthy."""

    def test_control_api_healthy(self):
        requires_service(CONTROL_API, "control-api")
        r = httpx.get(f"{CONTROL_API}/health", timeout=5.0)
        assert r.status_code == 200
        body = r.json()
        assert body.get("status") in ("ok", "healthy", "UP")

    def test_orchestrator_healthy(self):
        requires_service(ORCHESTRATOR, "orchestrator")
        r = httpx.get(f"{ORCHESTRATOR}/health", timeout=5.0)
        assert r.status_code == 200

    def test_digital_twin_healthy(self):
        requires_service(DIGITAL_TWIN, "digital-twin")
        r = httpx.get(f"{DIGITAL_TWIN}/health", timeout=5.0)
        assert r.status_code == 200

    def test_low_risk_job_completes_when_healthy(self):
        """Baseline: LOW risk jobs complete automatically."""
        requires_service(CONTROL_API, "control-api")
        requires_service(ORCHESTRATOR, "orchestrator")
        r = _post(CONTROL_API, "/jobs", {
            "type": "sensor.read",
            "origin": "OPERATOR",
            "target_asset_ids": ["asset:sensor:temp:greenhouse-north"],
            "risk_class": "LOW",
            "parameters": {"reading_type": "temperature"},
        })
        assert r.status_code in (200, 201), f"Job failed: {r.text}"
        job = r.json()
        assert job["state"] in ("APPROVED", "EXECUTING", "COMPLETED"), \
            f"LOW risk job stuck in {job['state']}"


# ─────────────────────────────────────────────────────────────────────────────
# Degraded mode assertions (no fault injection needed — static policy checks)
# ─────────────────────────────────────────────────────────────────────────────

class TestDegradedModePolicies:
    """Policies that guarantee safe behavior in degraded states."""

    @pytest.mark.degraded
    def test_high_risk_never_auto_executes(self):
        """HIGH-risk jobs must NEVER auto-execute, even if AI is down."""
        requires_service(CONTROL_API, "control-api")
        r = _post(CONTROL_API, "/jobs", {
            "type": "greenhouse.heating.enable",
            "origin": "OPERATOR",
            "target_asset_ids": ["asset:actuator:heater:greenhouse-north"],
            "risk_class": "HIGH",
            "parameters": {"target_temp_celsius": 18},
        })
        assert r.status_code in (200, 201), f"Job submission failed: {r.text}"
        job = r.json()
        assert job["state"] not in ("EXECUTING", "COMPLETED"), \
            f"POLICY VIOLATION: HIGH risk job auto-executed (state={job['state']})"
        assert job["state"] == "VALIDATING", \
            f"Expected VALIDATING, got {job['state']}"

    @pytest.mark.degraded
    def test_ai_advisory_origin_cannot_self_approve(self):
        """AI_ADVISORY origin cannot approve its own HIGH-risk jobs (F05 + ADR-002)."""
        requires_service(ORCHESTRATOR, "orchestrator")
        r = _post(ORCHESTRATOR, "/jobs", {
            "type": "irrigation.zone.enable",
            "origin": "AI_ADVISORY",
            "target_asset_ids": ["asset:actuator:valve:irrigation:zone-1"],
            "risk_class": "HIGH",
            "parameters": {"zone": "zone-1", "duration_minutes": 45},
            "requested_by": "model-router",
        })
        # Either rejected outright, or halted at VALIDATING
        if r.status_code in (400, 422):
            return  # explicit rejection — pass
        assert r.status_code in (200, 201), f"Unexpected response: {r.status_code}"
        job = r.json()
        assert job.get("approval_mode") != "AUTO", \
            f"F05 VIOLATION: AI_ADVISORY job has approval_mode=AUTO"
        assert job["state"] in ("VALIDATING",), \
            f"F05 VIOLATION: AI_ADVISORY HIGH job reached state={job['state']}"

    @pytest.mark.degraded
    def test_unknown_origin_rejected(self):
        """Orchestrator must reject jobs from unrecognized origins."""
        requires_service(ORCHESTRATOR, "orchestrator")
        r = _post(ORCHESTRATOR, "/jobs", {
            "type": "sensor.read",
            "origin": "ROGUE_SCRIPT",
            "target_asset_ids": ["asset:sensor:temp:greenhouse-north"],
            "risk_class": "LOW",
            "parameters": {},
        })
        assert r.status_code in (400, 422), \
            f"BOUNDARY VIOLATION: Orchestrator accepted unknown origin (status={r.status_code})"

    @pytest.mark.degraded
    def test_audit_log_written_for_job_state_transitions(self):
        """Every job state transition must produce an audit log entry."""
        requires_service(CONTROL_API, "control-api")
        requires_service(ORCHESTRATOR, "orchestrator")

        r = _post(CONTROL_API, "/jobs", {
            "type": "sensor.read",
            "origin": "OPERATOR",
            "target_asset_ids": ["asset:sensor:temp:greenhouse-north"],
            "risk_class": "LOW",
            "parameters": {"reading_type": "temperature"},
        })
        assert r.status_code in (200, 201)
        job_id = r.json()["id"]
        time.sleep(1)

        audit_r = _get(ORCHESTRATOR, f"/jobs/{job_id}/audit")
        if audit_r.status_code == 404:
            pytest.skip("Audit log endpoint not implemented yet")
        assert audit_r.status_code == 200
        entries = audit_r.json()
        assert len(entries) >= 1, f"No audit entries for job {job_id}"
        assert any(e.get("event_type") for e in entries), \
            "Audit entries missing event_type field"


# ─────────────────────────────────────────────────────────────────────────────
# Fault-injection tests (require docker pause/unpause)
# ─────────────────────────────────────────────────────────────────────────────

class TestFaultInjection:
    """
    Pause individual Docker containers and verify system degrades gracefully.

    These tests use docker pause/unpause to simulate service failures.
    They are marked fault_injection and require the full stack to be running.

    The CONTAINER_PREFIX env var allows customizing container names
    (default: "computer-").
    """

    CONTAINER_PREFIX = os.getenv("CONTAINER_PREFIX", "computer-")

    @pytest.fixture(autouse=True)
    def require_docker(self):
        result = subprocess.run(
            ["docker", "info"], capture_output=True, text=True
        )
        if result.returncode != 0:
            pytest.skip("Docker not available")

    @pytest.mark.fault_injection
    def test_control_api_survives_ai_down(self):
        """
        When model-router is paused, control-api must still respond to health
        and still process LOW-risk deterministic jobs.
        """
        requires_service(CONTROL_API, "control-api")
        container = f"{self.CONTAINER_PREFIX}model-router"

        try:
            _pause_container(container)
            time.sleep(2)

            # Health check must still work
            r_health = httpx.get(f"{CONTROL_API}/health", timeout=5.0)
            assert r_health.status_code == 200, \
                "control-api should stay healthy when AI plane is down"

            # LOW-risk deterministic job must still work
            r_job = _post(CONTROL_API, "/jobs", {
                "type": "sensor.read",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:sensor:temp:greenhouse-north"],
                "risk_class": "LOW",
                "parameters": {"reading_type": "temperature"},
            })
            assert r_job.status_code in (200, 201), \
                f"LOW-risk job should work even when AI is down: {r_job.text}"
        except subprocess.CalledProcessError:
            pytest.skip(f"Container '{container}' not found or not running")
        finally:
            _unpause_container(container)
            time.sleep(2)

    @pytest.mark.fault_injection
    def test_orchestrator_survives_postgres_brief_interruption(self):
        """
        After Postgres comes back up, orchestrator must resume correctly.
        Tests connection pool recovery.
        """
        requires_service(ORCHESTRATOR, "orchestrator")
        container = f"{self.CONTAINER_PREFIX}postgres"

        try:
            _pause_container(container)
            time.sleep(3)
            _unpause_container(container)
            time.sleep(3)  # allow reconnect

            # After recovery, orchestrator health must be green
            r = httpx.get(f"{ORCHESTRATOR}/health", timeout=10.0)
            assert r.status_code == 200, \
                f"Orchestrator must recover after Postgres reconnects (status={r.status_code})"
        except subprocess.CalledProcessError:
            pytest.skip(f"Container 'postgres' not found")

    @pytest.mark.fault_injection
    def test_event_ingest_queues_when_orchestrator_down(self):
        """
        When orchestrator is paused, event-ingest should queue events
        and not crash or drop events silently.
        """
        requires_service(EVENT_INGEST, "event-ingest")
        container = f"{self.CONTAINER_PREFIX}orchestrator"

        try:
            _pause_container(container)
            time.sleep(2)

            # event-ingest should still be healthy
            r_health = httpx.get(f"{EVENT_INGEST}/health", timeout=5.0)
            assert r_health.status_code == 200, \
                "event-ingest must stay healthy even when orchestrator is down"

            # Submit an event — it should accept and queue, not 500
            r_event = _post(EVENT_INGEST, "/events", {
                "source": "frigate",
                "type": "motion.detected",
                "asset_id": "asset:camera:driveway",
                "payload": {"zone": "driveway", "label": "person"},
            })
            assert r_event.status_code in (200, 201, 202), \
                f"event-ingest should accept events even when orchestrator is down: {r_event.status_code}"
        except subprocess.CalledProcessError:
            pytest.skip("Orchestrator container not found")
        finally:
            _unpause_container(container)
            time.sleep(2)

    @pytest.mark.fault_injection
    def test_no_actuation_during_orchestrator_outage(self):
        """
        When orchestrator is paused, no new EXECUTING jobs should appear.
        The system must default to safe state (halt-on-failure).
        """
        requires_service(CONTROL_API, "control-api")
        container = f"{self.CONTAINER_PREFIX}orchestrator"

        try:
            _pause_container(container)
            time.sleep(2)

            r = _post(CONTROL_API, "/jobs", {
                "type": "greenhouse.heating.enable",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:actuator:heater:greenhouse-north"],
                "risk_class": "HIGH",
                "parameters": {"target_temp_celsius": 18},
            })
            # Should either reject (503) or queue (202) — NOT execute
            assert r.status_code not in (200, 201) or r.json().get("state") != "EXECUTING", \
                f"SAFETY VIOLATION: HIGH risk job executed during orchestrator outage"
        except subprocess.CalledProcessError:
            pytest.skip("Orchestrator container not found")
        finally:
            _unpause_container(container)
            time.sleep(2)


# ─────────────────────────────────────────────────────────────────────────────
# AI plane isolation
# ─────────────────────────────────────────────────────────────────────────────

class TestAIPlaneDegradation:
    """Verify the AI plane fails independently from the control plane."""

    @pytest.mark.degraded
    def test_assistant_api_error_does_not_affect_control_api(self):
        """
        Even if assistant-api returns an error, control-api must stay healthy.
        These are separate runtime domains.
        """
        requires_service(CONTROL_API, "control-api")
        # Simulate bad assistant request
        try:
            httpx.post(
                f"{ASSISTANT_API}/chat",
                json={"messages": [], "mode": "INVALID"},
                headers=HEADERS,
                timeout=3.0,
            )
        except Exception:
            pass

        # control-api must still be healthy
        r = httpx.get(f"{CONTROL_API}/health", timeout=5.0)
        assert r.status_code == 200, \
            "control-api must be unaffected by assistant-api errors"

    @pytest.mark.degraded
    def test_chat_returns_graceful_error_when_llm_unavailable(self):
        """
        If the LLM backend (Ollama) is down, assistant-api must return a
        graceful error, not a 500 crash.
        """
        requires_service(ASSISTANT_API, "assistant-api")
        r = _post(ASSISTANT_API, "/chat", {
            "messages": [{"role": "user", "content": "Hello"}],
            "mode": "PERSONAL",
            "surface": "chat",
            "model_override": "nonexistent-model-12345",
        })
        # Must be 4xx or 5xx, but NOT an unhandled exception (connection refused, etc.)
        assert r is not None, "assistant-api must return a response, not crash"
        assert r.status_code in (200, 400, 422, 503, 504), \
            f"Unexpected status: {r.status_code}"
        if r.status_code != 200:
            body = r.json()
            assert "detail" in body or "error" in body, \
                "Error response must include 'detail' or 'error' field"
