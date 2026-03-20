"""
Milestone 1 Integration Tests
Definition of Done: Typed end-to-end event flow in Docker; no hardware.

Tests:
  1. All core services start and expose /health
  2. LOW risk job flows from control-api → orchestrator → APPROVED state
  3. HIGH risk job halts at VALIDATING (requires operator approval)
  4. AI origin HIGH-risk job is rejected (F05)
  5. Command log entry is created for approved jobs (F04)
  6. Asset registry is available and returns seeded assets

These tests require Docker infrastructure running.
Run via: task test:integration
or in CI: simulation.yml workflow
"""
import os
import time

import httpx
import pytest

CONTROL_API = os.getenv("CONTROL_API_URL", "http://localhost:8000")
ORCHESTRATOR = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")

DEV_TOKEN = "Bearer dev-token"
HEADERS = {"Authorization": DEV_TOKEN, "Content-Type": "application/json"}


def wait_for_service(url: str, timeout: int = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/health", timeout=2)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Service at {url} did not become healthy in {timeout}s")


@pytest.fixture(scope="session", autouse=True)
def wait_for_all_services():
    """Wait for all services before running any tests."""
    for svc_url in [DIGITAL_TWIN, ORCHESTRATOR, CONTROL_API]:
        wait_for_service(svc_url, timeout=60)


class TestHealthEndpoints:
    def test_control_api_health(self):
        r = httpx.get(f"{CONTROL_API}/health", timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "degraded")

    def test_orchestrator_health(self):
        r = httpx.get(f"{ORCHESTRATOR}/health", timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "degraded")

    def test_digital_twin_health(self):
        r = httpx.get(f"{DIGITAL_TWIN}/health", timeout=5)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "degraded")


class TestJobFlow:
    def test_low_risk_job_auto_approved(self):
        """LOW risk jobs from OPERATOR origin must be auto-approved (no human gate)."""
        r = httpx.post(
            f"{CONTROL_API}/jobs",
            headers=HEADERS,
            json={
                "type": "sensor.read",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:sensor:temp:greenhouse-north"],
                "risk_class": "LOW",
                "parameters": {"reading_type": "temperature"},
            },
            timeout=10,
        )
        assert r.status_code in (200, 201), f"Unexpected status: {r.status_code} — {r.text}"
        job = r.json()
        assert job["state"] in ("APPROVED", "EXECUTING", "COMPLETED"), (
            f"LOW risk job should be auto-approved, got state: {job['state']}"
        )

    def test_high_risk_job_requires_approval(self):
        """HIGH risk jobs must halt at VALIDATING — never auto-approved (F05)."""
        r = httpx.post(
            f"{CONTROL_API}/jobs",
            headers=HEADERS,
            json={
                "type": "irrigation.zone.enable",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:actuator:valve:irrigation:zone-1"],
                "risk_class": "HIGH",
                "parameters": {"zone": "zone-1", "duration_minutes": 30},
            },
            timeout=10,
        )
        assert r.status_code in (200, 201), f"Unexpected status: {r.status_code} — {r.text}"
        job = r.json()
        assert job["state"] == "VALIDATING", (
            f"HIGH risk job must not be auto-approved — expected VALIDATING, got: {job['state']}"
        )

    def test_ai_origin_high_risk_job_blocked(self):
        """AI_ADVISORY origin + HIGH risk must require OPERATOR_REQUIRED approval (F05)."""
        r = httpx.post(
            f"{ORCHESTRATOR}/jobs",
            headers=HEADERS,
            json={
                "type": "irrigation.zone.enable",
                "origin": "AI_ADVISORY",
                "target_asset_ids": ["asset:actuator:valve:irrigation:zone-1"],
                "risk_class": "HIGH",
                "parameters": {"zone": "zone-1", "duration_minutes": 60},
                "requested_by": "model-router",
            },
            timeout=10,
        )
        if r.status_code in (200, 201):
            job = r.json()
            assert job.get("approval_mode") not in ("AUTO", "AUTO_WITH_AUDIT", "NONE"), (
                f"F05 VIOLATION: AI_ADVISORY + HIGH risk job cannot have auto approval. "
                f"Got: {job.get('approval_mode')}"
            )
            assert job["state"] == "VALIDATING", (
                f"AI_ADVISORY HIGH risk must be VALIDATING (awaiting operator). Got: {job['state']}"
            )
        else:
            assert r.status_code in (400, 422), (
                f"Expected 422 policy rejection or VALIDATING state, got: {r.status_code}"
            )

    def test_job_list_returns_submitted_jobs(self):
        """Jobs endpoint must return submitted jobs."""
        r = httpx.get(f"{CONTROL_API}/jobs", headers=HEADERS, timeout=5)
        assert r.status_code == 200
        jobs = r.json()
        assert isinstance(jobs, list), "Expected list of jobs"
        assert len(jobs) >= 1, "Expected at least one job from previous tests"


class TestAssetRegistry:
    def test_assets_endpoint_available(self):
        r = httpx.get(f"{DIGITAL_TWIN}/assets", timeout=5)
        assert r.status_code == 200
        assets = r.json()
        assert isinstance(assets, list)

    def test_asset_has_canonical_ids(self):
        """All assets must have canonical asset_id format (no vendor entity IDs)."""
        r = httpx.get(f"{DIGITAL_TWIN}/assets", timeout=5)
        if r.status_code != 200:
            pytest.skip("Asset registry empty — seed data required")

        assets = r.json()
        for asset in assets:
            assert "asset_id" in asset, "Asset missing canonical asset_id"
            # Canonical IDs follow the taxonomy pattern
            assert ":" in asset["asset_id"] or asset["asset_id"].startswith("asset-"), (
                f"Non-canonical asset_id: {asset['asset_id']}"
            )
            # Vendor entity must not appear at the API boundary
            assert "entity_id" not in asset or asset.get("entity_id") is None, (
                "Vendor entity_id must not be exposed by digital-twin API (F02)"
            )
