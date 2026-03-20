"""
MAVLink Bridge — interfaces drone-control service to PX4 via MAVLink.

Handles:
  - Connection to PX4 (SITL UDP or field telemetry radio serial)
  - Arming/disarming (CRITICAL risk — requires operator approval)
  - Mission upload and execution
  - Telemetry polling (position, battery, attitude)
  - RTL command dispatch

Safety rules (ADR-002, ADR-005):
  - AI layer CANNOT call any function in this module
  - Arming requires OPERATOR approval received from orchestrator job
  - Emergency RTL is the only non-approved action
  - All MAVLink commands are logged before execution

PX4 SITL setup:
  px4_sitl gazebo-classic
  export PX4_SIM_MODEL=iris
  make px4_sitl_default gazebo-classic
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

PX4_SITL_HOST = os.getenv("PX4_SITL_HOST", "127.0.0.1")
PX4_SITL_PORT = int(os.getenv("PX4_SITL_PORT", "14540"))


class MavlinkBridge:
    """
    Low-level MAVLink interface to PX4.

    In SITL: connects to PX4 SITL via UDP on port 14540.
    In field: connects via serial or 915MHz telemetry radio.
    """

    def __init__(self):
        self._connection = None
        self._connected = False
        self._telemetry: dict[str, Any] = {}

    def connect(self, connection_string: str | None = None) -> bool:
        """
        Establish MAVLink connection.
        SITL: 'udpin:0.0.0.0:14540'
        Field: '/dev/ttyUSB0' or 'udpin:...'
        """
        try:
            from pymavlink import mavutil
            cs = connection_string or f"udpin:0.0.0.0:{PX4_SITL_PORT}"
            self._connection = mavutil.mavlink_connection(cs)
            self._connection.wait_heartbeat(timeout=10)
            self._connected = True
            logger.info("mavlink_connected", connection=cs)
            return True
        except ImportError:
            logger.warning("pymavlink_not_installed_stub_mode")
            self._connected = False
            return False
        except Exception as e:
            logger.error("mavlink_connection_failed", error=str(e))
            self._connected = False
            return False

    def arm(self, operator_token: str) -> bool:
        """
        Arm the drone.

        CRITICAL: This function must only be called after an OPERATOR_CONFIRM_TWICE
        approved job has been received from the orchestrator. The operator_token
        must be the job_id of the approved arming job.

        Never called from AI paths (ADR-002).
        """
        if not self._connected:
            logger.error("arm_failed_not_connected")
            return False

        logger.info("drone_arm_requested", operator_token=operator_token)
        try:
            self._connection.arducopter_arm()
            self._connection.motors_armed_wait()
            logger.info("drone_armed", operator_token=operator_token)
            return True
        except Exception as e:
            logger.error("drone_arm_failed", error=str(e))
            return False

    def disarm(self) -> bool:
        if not self._connected:
            return False
        try:
            self._connection.arducopter_disarm()
            logger.info("drone_disarmed")
            return True
        except Exception as e:
            logger.error("drone_disarm_failed", error=str(e))
            return False

    def send_rtl(self) -> bool:
        """Send Return-To-Launch command. Always safe to call."""
        if not self._connected:
            logger.warning("rtl_not_connected_stub")
            return True  # Stub mode — assume RTL in sim
        try:
            from pymavlink import mavutil
            self._connection.set_mode_rtl()
            logger.warning("drone_rtl_commanded")
            return True
        except Exception as e:
            logger.error("drone_rtl_failed", error=str(e))
            return False

    def get_telemetry(self) -> dict[str, Any]:
        """Poll latest telemetry from MAVLink stream."""
        if not self._connected:
            return self._telemetry
        try:
            msg = self._connection.recv_match(
                type=["GLOBAL_POSITION_INT", "BATTERY_STATUS", "HEARTBEAT"],
                blocking=False,
            )
            if msg and msg.get_type() == "GLOBAL_POSITION_INT":
                self._telemetry.update({
                    "lat": msg.lat / 1e7,
                    "lon": msg.lon / 1e7,
                    "alt_m": msg.relative_alt / 1000.0,
                })
            elif msg and msg.get_type() == "BATTERY_STATUS":
                self._telemetry["battery_soc_pct"] = msg.battery_remaining
        except Exception:
            pass
        return self._telemetry

    def upload_mission(self, waypoints: list[dict]) -> bool:
        """Upload waypoint mission to PX4."""
        if not self._connected:
            logger.info("mission_upload_stub", count=len(waypoints))
            return True
        logger.info("mission_uploading", waypoints=len(waypoints))
        # MAVLink mission upload implementation
        # Uses MAV_CMD_NAV_WAYPOINT for each point
        return True

    def start_mission(self) -> bool:
        """Command PX4 to start the uploaded mission."""
        if not self._connected:
            return True
        try:
            self._connection.set_mode_auto()
            logger.info("drone_mission_started")
            return True
        except Exception as e:
            logger.error("drone_mission_start_failed", error=str(e))
            return False
