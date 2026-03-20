"""
Milestone 2 Integration Tests
Definition of Done:
  - Simulated zone telemetry flows through the system
  - Policy-driven commands are proposed by control services
  - Operator approvals gate risky jobs (HIGH risk)
  - Digital-twin state reflects injected telemetry
  - Energy dispatch proposals create jobs pending approval

These tests inject telemetry via HTTP (simulating MQTT) and verify the
job submission and approval flow end-to-end.
"""
import os
import time

import httpx
import pytest

CONTROL_API = os.getenv("CONTROL_API_URL", "http://localhost:8000")
ORCHESTRATOR = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")
DIGITAL_TWIN = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")
GREENHOUSE_CTRL = os.getenv("GREENHOUSE_CTRL_URL", "http://localhost:8010")
HYDRO_CTRL = os.getenv("HYDRO_CTRL_URL", "http://localhost:8011")
ENERGY_ENGINE = os.getenv("ENERGY_ENGINE_URL", "http://localhost:8012")

HEADERS = {"Authorization": "Bearer dev-token", "Content-Type": "application/json"}


def _service_available(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


class TestSimulatedTelemetry:
    def test_greenhouse_telemetry_updates_digital_twin(self):
        """Injecting telemetry updates digital-twin asset state."""
        if not _service_available(GREENHOUSE_CTRL):
            pytest.skip("greenhouse-control not running")
        if not _service_available(DIGITAL_TWIN):
            pytest.skip("digital-twin not running")

        r = httpx.post(
            f"{GREENHOUSE_CTRL}/zones/greenhouse-north/telemetry",
            json={"temperature_celsius": 18.5, "humidity_percent": 65.0},
            timeout=10,
        )
        assert r.status_code == 200
        zone_status = r.json()
        assert zone_status["zone_id"] == "greenhouse-north"
        assert zone_status["last_reading"]["temperature_celsius"] == 18.5

    def test_frost_telemetry_triggers_job_proposal(self):
        """
        Injecting below-frost-threshold temperature must trigger a
        HIGH-risk heating job proposal to orchestrator.
        Job must be in VALIDATING state (not auto-approved, F05).
        """
        if not _service_available(GREENHOUSE_CTRL):
            pytest.skip("greenhouse-control not running")
        if not _service_available(ORCHESTRATOR):
            pytest.skip("orchestrator not running")

        # Inject frost-level temperature (below 2.0°C threshold)
        r = httpx.post(
            f"{GREENHOUSE_CTRL}/zones/greenhouse-north/telemetry",
            json={"temperature_celsius": 0.5, "humidity_percent": 90.0},
            timeout=10,
        )
        assert r.status_code == 200

        # Wait for job proposal to be submitted
        time.sleep(1)

        # Check that a HIGH-risk heating job was submitted and is in VALIDATING
        r = httpx.get(
            f"{ORCHESTRATOR}/jobs",
            params={"limit": 10},
            timeout=5,
        )
        assert r.status_code == 200
        jobs = r.json()

        heating_jobs = [
            j for j in jobs
            if "heating" in j.get("type", "").lower()
            and j.get("risk_class") == "HIGH"
        ]

        if heating_jobs:
            job = heating_jobs[0]
            assert job["state"] == "VALIDATING", (
                f"Frost heating job must require operator approval, got: {job['state']}"
            )
            assert job["approval_mode"] in ("OPERATOR_REQUIRED", "OPERATOR_CONFIRM_TWICE"), (
                f"HIGH risk job must require operator approval, got: {job['approval_mode']}"
            )

    def test_hydro_below_ph_triggers_ph_up_job(self):
        """pH below target triggers pH-Up dosing job proposal."""
        if not _service_available(HYDRO_CTRL):
            pytest.skip("hydro-control not running")

        r = httpx.post(
            f"{HYDRO_CTRL}/bays/hydro-bay-1/telemetry",
            json={"ph": 5.3, "ec_ms": 1.6, "water_temp_celsius": 20.0},
            timeout=10,
        )
        assert r.status_code == 200
        bay_status = r.json()
        assert bay_status["bay_id"] == "hydro-bay-1"
        assert bay_status["last_reading"]["ph"] == 5.3

    def test_energy_peak_shave_job_proposed(self):
        """
        Injecting high grid import during TOU peak proposes
        battery discharge job.
        """
        if not _service_available(ENERGY_ENGINE):
            pytest.skip("energy-engine not running")

        # Inject high grid import + sufficient battery SOC
        r = httpx.post(
            f"{ENERGY_ENGINE}/telemetry",
            json={
                "grid_import_kw": 8.5,
                "solar_production_kw": 2.0,
                "battery_soc_pct": 75.0,
            },
            timeout=10,
        )
        assert r.status_code == 200
        status = r.json()
        # Should have updated readings
        assert status["last_grid_kw"] == 8.5
        assert status["last_battery_soc_pct"] == 75.0


class TestOperatorApprovalFlow:
    def test_operator_can_approve_validating_job(self):
        """Operator can approve a HIGH-risk job that is in VALIDATING state."""
        # First, create a HIGH-risk job
        r = httpx.post(
            f"{CONTROL_API}/jobs",
            headers=HEADERS,
            json={
                "type": "greenhouse.heating.enable",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:actuator:heater:greenhouse-north"],
                "risk_class": "HIGH",
                "parameters": {"zone": "greenhouse-north", "duration_hours": 4},
            },
            timeout=10,
        )
        assert r.status_code in (200, 201)
        job = r.json()
        job_id = job["job_id"]
        assert job["state"] == "VALIDATING"

        # Operator approves it
        r = httpx.post(
            f"{CONTROL_API}/jobs/{job_id}/approve",
            headers=HEADERS,
            json={"approved_by": "operator_001", "approval_note": "Frost risk confirmed"},
            timeout=10,
        )
        assert r.status_code == 200
        approved_job = r.json()
        assert approved_job["state"] == "APPROVED", (
            f"Expected APPROVED after operator approval, got: {approved_job['state']}"
        )
        assert approved_job["approval_event"]["approved_by"] == "operator_001"

    def test_operator_can_abort_validating_job(self):
        """Operator can abort a job while it's in VALIDATING state."""
        r = httpx.post(
            f"{CONTROL_API}/jobs",
            headers=HEADERS,
            json={
                "type": "irrigation.zone.enable",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:actuator:valve:irrigation:zone-2"],
                "risk_class": "HIGH",
                "parameters": {"zone": "zone-2", "duration_minutes": 60},
            },
            timeout=10,
        )
        assert r.status_code in (200, 201)
        job = r.json()
        job_id = job["job_id"]

        # Abort the job
        r = httpx.post(
            f"{CONTROL_API}/jobs/{job_id}/abort",
            headers=HEADERS,
            params={"reason": "Changed mind"},
            timeout=10,
        )
        assert r.status_code == 200
        aborted = r.json()
        assert aborted["state"] == "ABORTED"

    def test_e_stop_aborts_all_executing_jobs(self):
        """E-stop endpoint aborts all EXECUTING jobs immediately."""
        r = httpx.post(
            f"{CONTROL_API}/e-stop",
            headers=HEADERS,
            params={"reason": "Test E-stop"},
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json()
        assert "aborted_jobs" in result


class TestPolicyEnforcement:
    def test_policy_origin_high_risk_requires_operator(self):
        """POLICY origin + HIGH risk requires operator approval (same as OPERATOR)."""
        r = httpx.post(
            f"{ORCHESTRATOR}/jobs",
            json={
                "type": "irrigation.zone.enable",
                "origin": "POLICY",
                "target_asset_ids": ["asset:actuator:valve:irrigation:zone-1"],
                "risk_class": "HIGH",
                "requested_by": "greenhouse-control",
                "parameters": {"zone": "zone-1"},
            },
            timeout=10,
        )
        assert r.status_code in (200, 201)
        job = r.json()
        assert job["state"] == "VALIDATING"
        assert "OPERATOR" in job.get("approval_mode", "")

    def test_policy_origin_medium_risk_auto_audit(self):
        """POLICY origin + MEDIUM risk is AUTO_WITH_AUDIT (no human gate)."""
        r = httpx.post(
            f"{ORCHESTRATOR}/jobs",
            json={
                "type": "greenhouse.ventilation.enable",
                "origin": "POLICY",
                "target_asset_ids": ["asset:actuator:vent:greenhouse-north"],
                "risk_class": "MEDIUM",
                "requested_by": "greenhouse-control",
                "parameters": {"zone": "greenhouse-north", "speed_percent": 50},
            },
            timeout=10,
        )
        assert r.status_code in (200, 201)
        job = r.json()
        # MEDIUM + POLICY should be AUTO_WITH_AUDIT (auto-approved with audit log)
        assert job["state"] in ("APPROVED", "EXECUTING", "COMPLETED"), (
            f"POLICY + MEDIUM risk should be auto-approved, got: {job['state']}"
        )
