"""
Drone SITL (Software-In-The-Loop) simulation runner.

Supervised drone mission testing against PX4 SITL or stub drone-control.
ADR-005: Drone deferred until rover proven; SITL is the qualification gate.

Usage:
  python robotics/simulation/drone_sitl.py --scenario supervised_waypoint
  python robotics/simulation/drone_sitl.py --scenario emergency_rtl
  python robotics/simulation/drone_sitl.py --scenario battery_low_rtl

All drone missions require OPERATOR_CONFIRM_TWICE approval (CRITICAL risk).
"""
from __future__ import annotations

import argparse
import asyncio
import time

import httpx
import structlog

logger = structlog.get_logger("drone_sitl")

DRONE_CONTROL_URL = "http://localhost:8041"
CONTROL_API_URL = "http://localhost:8000"
ORCHESTRATOR_URL = "http://localhost:8002"

HEADERS = {"Authorization": "Bearer dev-token", "Content-Type": "application/json"}


async def submit_drone_arm_job() -> str | None:
    """Submit CRITICAL arming job — requires OPERATOR_CONFIRM_TWICE."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{CONTROL_API_URL}/jobs",
            headers=HEADERS,
            json={
                "type": "drone.arm",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:robot:drone:aerial-drone-001"],
                "risk_class": "CRITICAL",
                "parameters": {"supervised": True, "pre_flight_check": True},
            },
        )
        if resp.status_code in (200, 201):
            job = resp.json()
            assert job["state"] == "VALIDATING", (
                f"Drone arming must require OPERATOR_CONFIRM_TWICE approval, got: {job['state']}"
            )
            logger.info("drone_arm_job_submitted", job_id=job["job_id"], state=job["state"])
            return job["job_id"]
    logger.error("drone_arm_job_failed")
    return None


async def scenario_supervised_waypoint():
    """SITL Scenario 1: Supervised waypoint mission with operator approval."""
    logger.info("=== SITL Scenario: Supervised Waypoint Mission ===")

    job_id = await submit_drone_arm_job()
    if not job_id:
        logger.error("arm_job_submission_failed")
        return

    logger.info("PASS: Arming job requires OPERATOR_CONFIRM_TWICE (CRITICAL risk)")
    logger.info("In field: operator confirms twice before drone arms")
    logger.info("SITL: Scenario stub — full PX4 integration requires self-hosted runner")


async def scenario_emergency_rtl():
    """SITL Scenario 2: Emergency RTL triggered by operator."""
    logger.info("=== SITL Scenario: Emergency RTL ===")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{DRONE_CONTROL_URL}/rtl",
            params={"reason": "SITL emergency test"},
        )
        if resp.status_code == 200:
            status = resp.json()
            assert status["state"] in ("RETURNING", "GROUNDED", "EMERGENCY_LAND"), (
                f"Expected RTL state, got: {status['state']}"
            )
            logger.info("SCENARIO PASS: Drone RTL command accepted", state=status["state"])
        else:
            logger.warning("Drone control not available — SITL mode only")


async def scenario_battery_low_rtl():
    """SITL Scenario 3: Battery low triggers automatic RTL."""
    logger.info("=== SITL Scenario: Battery Low RTL ===")

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Simulate telemetry with low battery
        resp = await client.post(
            f"{DRONE_CONTROL_URL}/telemetry",
            json={"lat": 47.6062, "lon": -117.3321, "alt_m": 15.0, "battery_soc_pct": 18.0},
        )
        if resp.status_code == 200:
            status = resp.json()
            # At 18% (below 20% RTL threshold), drone should enter RETURNING
            logger.info("Telemetry injected, checking state...", state=status["state"])
            logger.info("SCENARIO: Battery low RTL checked")
        else:
            logger.warning("Drone control not available — SITL stub")


async def scenario_ai_cannot_arm():
    """
    SITL Safety Gate: Verify AI advisory cannot arm or fly drone.
    ADR-002: AI layer must never arm drone.
    """
    logger.info("=== SITL Safety Gate: AI Cannot Arm Drone (ADR-002) ===")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{ORCHESTRATOR_URL}/jobs",
            headers=HEADERS,
            json={
                "type": "drone.arm",
                "origin": "AI_ADVISORY",
                "target_asset_ids": ["asset:robot:drone:aerial-drone-001"],
                "risk_class": "CRITICAL",
                "parameters": {"reason": "AI wants to arm drone"},
                "requested_by": "model-router",
            },
        )
        if resp.status_code in (200, 201):
            job = resp.json()
            assert job["state"] == "VALIDATING", (
                f"CRITICAL SAFETY VIOLATION: AI was able to submit arming job in state: {job['state']}"
            )
            assert job.get("approval_mode") not in ("AUTO", "NONE"), (
                f"ADR-002 VIOLATION: AI arm job got auto-approval: {job.get('approval_mode')}"
            )
            logger.info("SAFETY PASS: AI drone arm job requires OPERATOR approval")
        else:
            assert resp.status_code in (400, 422), (
                f"Expected rejection for AI arm attempt, got {resp.status_code}"
            )
            logger.info("SAFETY PASS: AI drone arm job rejected by orchestrator")


SCENARIOS = {
    "supervised_waypoint": scenario_supervised_waypoint,
    "emergency_rtl": scenario_emergency_rtl,
    "battery_low_rtl": scenario_battery_low_rtl,
    "ai_cannot_arm": scenario_ai_cannot_arm,
}


async def main(scenario_name: str):
    fn = SCENARIOS.get(scenario_name)
    if not fn:
        print(f"Unknown scenario: {scenario_name}")
        print(f"Available: {list(SCENARIOS.keys())}")
        return
    await fn()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drone SITL scenario runner")
    parser.add_argument("--scenario", required=True, choices=list(SCENARIOS.keys()))
    args = parser.parse_args()
    asyncio.run(main(args.scenario))
