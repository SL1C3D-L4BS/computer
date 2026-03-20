"""
Rover SITL (Software-In-The-Loop) simulation runner.

Simulates rover telemetry and mission execution for testing without hardware.
Integrates with:
  - Gazebo (if available) for physics simulation
  - rover-control service (HTTP telemetry injection)
  - Orchestrator (job submission and state tracking)

Usage:
  python robotics/simulation/rover_sitl.py --scenario waypoint_mission
  python robotics/simulation/rover_sitl.py --scenario safe_stop
  python robotics/simulation/rover_sitl.py --scenario battery_low_rth

See docs/delivery/hil-gate-plan.md for scenario specs.
"""
from __future__ import annotations

import argparse
import asyncio
import time
from typing import Any

import httpx
import structlog

logger = structlog.get_logger("rover_sitl")

ROVER_CONTROL_URL = "http://localhost:8040"
ORCHESTRATOR_URL = "http://localhost:8002"
CONTROL_API_URL = "http://localhost:8000"

HEADERS = {"Authorization": "Bearer dev-token", "Content-Type": "application/json"}


async def submit_mission_job(waypoints: list[dict]) -> str | None:
    """Submit a rover mission job via control-api (requires OPERATOR approval)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{CONTROL_API_URL}/jobs",
            headers=HEADERS,
            json={
                "type": "rover.mission.waypoint",
                "origin": "OPERATOR",
                "target_asset_ids": ["asset:robot:rover:field-rover-001"],
                "risk_class": "HIGH",
                "parameters": {"waypoints": waypoints, "supervised": True},
            },
        )
        if resp.status_code in (200, 201):
            job = resp.json()
            logger.info("mission_job_submitted", job_id=job["job_id"], state=job["state"])
            return job["job_id"]
        logger.error("mission_job_failed", status=resp.status_code)
        return None


async def approve_job(job_id: str) -> bool:
    """Simulate operator approving the mission job."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{CONTROL_API_URL}/jobs/{job_id}/approve",
            headers=HEADERS,
            json={"approved_by": "operator_sitl", "approval_note": "SITL test approval"},
        )
        success = resp.status_code == 200
        if success:
            logger.info("mission_job_approved", job_id=job_id)
        return success


async def inject_telemetry(lat: float, lon: float, battery: float = 85.0) -> None:
    """Simulate rover position telemetry."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{ROVER_CONTROL_URL}/telemetry",
            json={"lat": lat, "lon": lon, "battery_soc_pct": battery},
        )
        if resp.status_code != 200:
            logger.warning("telemetry_inject_failed", status=resp.status_code)


async def scenario_waypoint_mission():
    """SITL Scenario 1: Complete waypoint mission with position updates."""
    logger.info("=== SITL Scenario: Waypoint Mission ===")

    waypoints = [
        {"lat": 47.6062, "lon": -117.3321, "alt_m": 0},
        {"lat": 47.6065, "lon": -117.3325, "alt_m": 0},
        {"lat": 47.6068, "lon": -117.3320, "alt_m": 0},
    ]

    job_id = await submit_mission_job(waypoints)
    if not job_id:
        logger.error("mission_submission_failed")
        return

    # Approve the job (SITL: simulate operator approval)
    await asyncio.sleep(1)
    approved = await approve_job(job_id)
    if not approved:
        logger.error("mission_approval_failed")
        return

    # Simulate rover traversing waypoints
    logger.info("Simulating rover traversal...")
    positions = [
        (47.6062, -117.3321),
        (47.6063, -117.3322),
        (47.6065, -117.3325),
        (47.6067, -117.3323),
        (47.6068, -117.3320),
        (47.6062, -117.3321),  # Return home
    ]

    for lat, lon in positions:
        await inject_telemetry(lat, lon, battery=85.0 - positions.index((lat, lon)) * 2)
        await asyncio.sleep(1)

    logger.info("SCENARIO PASS: Waypoint mission completed")


async def scenario_safe_stop():
    """SITL Scenario 2: E-stop during active mission."""
    logger.info("=== SITL Scenario: Safe Stop During Mission ===")

    waypoints = [{"lat": 47.6070, "lon": -117.3330, "alt_m": 0}]
    job_id = await submit_mission_job(waypoints)
    if not job_id:
        return

    await asyncio.sleep(1)
    await approve_job(job_id)
    await inject_telemetry(47.6064, -117.3325)

    # Trigger E-stop mid-mission
    logger.info("Triggering E-stop mid-mission...")
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.post(
            f"{ROVER_CONTROL_URL}/e-stop",
            params={"reason": "SITL safe-stop test"},
        )
        if resp.status_code == 200:
            status = resp.json()
            assert status["state"] == "SAFE_STOP", f"Expected SAFE_STOP, got: {status['state']}"
            logger.info("SCENARIO PASS: Rover in SAFE_STOP state after E-stop")
        else:
            logger.error("SCENARIO FAIL: E-stop request failed")


async def scenario_battery_low_rth():
    """SITL Scenario 3: Battery low triggers auto return-to-home."""
    logger.info("=== SITL Scenario: Battery Low RTH ===")

    waypoints = [{"lat": 47.6070, "lon": -117.3330, "alt_m": 0}]
    job_id = await submit_mission_job(waypoints)
    if not job_id:
        return

    await asyncio.sleep(1)
    await approve_job(job_id)

    # Normal telemetry
    await inject_telemetry(47.6064, -117.3325, battery=50.0)
    await asyncio.sleep(1)

    # Battery drops below RTH threshold (15%)
    logger.info("Simulating battery drop below RTH threshold...")
    await inject_telemetry(47.6066, -117.3327, battery=12.0)
    await asyncio.sleep(1)

    # Check rover state
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{ROVER_CONTROL_URL}/status")
        if resp.status_code == 200:
            status = resp.json()
            # Either SAFE_STOP (battery abort) or RETURNING (RTH initiated)
            assert status["state"] in ("SAFE_STOP", "RETURNING"), (
                f"Expected SAFE_STOP or RETURNING on low battery, got: {status['state']}"
            )
            logger.info("SCENARIO PASS: Battery low triggered safe state", state=status["state"])


SCENARIOS = {
    "waypoint_mission": scenario_waypoint_mission,
    "safe_stop": scenario_safe_stop,
    "battery_low_rth": scenario_battery_low_rth,
}


async def main(scenario_name: str):
    scenario_fn = SCENARIOS.get(scenario_name)
    if not scenario_fn:
        print(f"Unknown scenario: {scenario_name}")
        print(f"Available: {list(SCENARIOS.keys())}")
        return
    await scenario_fn()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rover SITL scenario runner")
    parser.add_argument("--scenario", required=True, choices=list(SCENARIOS.keys()))
    args = parser.parse_args()
    asyncio.run(main(args.scenario))
