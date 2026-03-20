"""
Tests for RoverMissionStateMachine.

Validates:
  - Initial state
  - Valid and invalid state transitions
  - E-stop from any state
  - Battery RTH threshold logic
  - Communication timeout detection
  - Mission log audit trail
"""
from __future__ import annotations

from datetime import datetime, timedelta
import pytest
from rover_control.mission_state_machine import (
    MissionState,
    RoverMissionStateMachine,
    BATTERY_RTH_THRESHOLD_PCT,
    BATTERY_ABORT_THRESHOLD_PCT,
    COMMS_TIMEOUT_SECONDS,
)


@pytest.fixture
def rover():
    return RoverMissionStateMachine("rover-test-001")


def _advance_to_navigating(rover: RoverMissionStateMachine) -> None:
    rover.transition(MissionState.DISPATCHING)
    rover.transition(MissionState.NAVIGATING)


class TestInitialState:
    def test_starts_idle(self, rover: RoverMissionStateMachine):
        assert rover.state == MissionState.IDLE

    def test_has_rover_id(self, rover: RoverMissionStateMachine):
        assert rover.rover_id == "rover-test-001"

    def test_mission_log_empty(self, rover: RoverMissionStateMachine):
        assert rover.mission_log == []

    def test_battery_starts_none(self, rover: RoverMissionStateMachine):
        assert rover.battery_soc_pct is None


class TestValidTransitions:
    def test_idle_to_dispatching(self, rover: RoverMissionStateMachine):
        rover.transition(MissionState.DISPATCHING)
        assert rover.state == MissionState.DISPATCHING

    def test_dispatching_to_navigating(self, rover: RoverMissionStateMachine):
        rover.transition(MissionState.DISPATCHING)
        rover.transition(MissionState.NAVIGATING)
        assert rover.state == MissionState.NAVIGATING

    def test_navigating_to_at_waypoint(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.AT_WAYPOINT)
        assert rover.state == MissionState.AT_WAYPOINT

    def test_at_waypoint_to_collecting(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.AT_WAYPOINT)
        rover.transition(MissionState.COLLECTING_DATA)
        assert rover.state == MissionState.COLLECTING_DATA

    def test_collecting_to_navigating(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.AT_WAYPOINT)
        rover.transition(MissionState.COLLECTING_DATA)
        rover.transition(MissionState.NAVIGATING, reason="Next waypoint")
        assert rover.state == MissionState.NAVIGATING

    def test_navigating_to_returning(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.RETURNING)
        assert rover.state == MissionState.RETURNING

    def test_returning_to_docked(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.RETURNING)
        rover.transition(MissionState.DOCKED)
        assert rover.state == MissionState.DOCKED

    def test_docked_to_idle(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.RETURNING)
        rover.transition(MissionState.DOCKED)
        rover.transition(MissionState.IDLE)
        assert rover.state == MissionState.IDLE


class TestInvalidTransitions:
    def test_idle_cannot_go_directly_to_navigating(self, rover: RoverMissionStateMachine):
        with pytest.raises(ValueError, match="Invalid transition"):
            rover.transition(MissionState.NAVIGATING)

    def test_idle_cannot_go_to_at_waypoint(self, rover: RoverMissionStateMachine):
        with pytest.raises(ValueError, match="Invalid transition"):
            rover.transition(MissionState.AT_WAYPOINT)

    def test_docked_cannot_navigate_directly(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.RETURNING)
        rover.transition(MissionState.DOCKED)
        with pytest.raises(ValueError, match="Invalid transition"):
            rover.transition(MissionState.NAVIGATING)


class TestEStop:
    def test_estop_from_idle(self, rover: RoverMissionStateMachine):
        rover.e_stop(reason="Test E-stop from idle")
        assert rover.state == MissionState.SAFE_STOP

    def test_estop_from_navigating(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.e_stop(reason="Obstacle detected")
        assert rover.state == MissionState.SAFE_STOP

    def test_estop_from_collecting(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.transition(MissionState.AT_WAYPOINT)
        rover.transition(MissionState.COLLECTING_DATA)
        rover.e_stop()
        assert rover.state == MissionState.SAFE_STOP

    def test_estop_logged(self, rover: RoverMissionStateMachine):
        rover.e_stop(reason="Emergency stop reason")
        assert len(rover.mission_log) > 0
        assert "Emergency stop reason" in rover.mission_log[-1]["reason"]

    def test_clear_fault_from_safe_stop(self, rover: RoverMissionStateMachine):
        rover.e_stop()
        rover.clear_fault(operator_id="operator_001")
        assert rover.state == MissionState.IDLE

    def test_clear_fault_requires_safe_stop_or_fault(self, rover: RoverMissionStateMachine):
        # Cannot clear fault when IDLE (not in fault state)
        with pytest.raises(ValueError):
            rover.clear_fault(operator_id="operator_001")


class TestBatteryManagement:
    def test_normal_battery_no_rth(self, rover: RoverMissionStateMachine):
        triggered = rover.update_battery(85.0)
        assert triggered is False
        assert rover.state == MissionState.IDLE

    def test_battery_below_rth_triggers_rth_during_mission(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        triggered = rover.update_battery(BATTERY_RTH_THRESHOLD_PCT - 1.0)
        assert triggered is True

    def test_battery_below_abort_threshold_triggers_safe_stop(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.update_battery(BATTERY_ABORT_THRESHOLD_PCT - 1.0)
        assert rover.state in (MissionState.SAFE_STOP, MissionState.RETURNING)

    def test_battery_level_recorded(self, rover: RoverMissionStateMachine):
        rover.update_battery(45.0)
        assert rover.battery_soc_pct == 45.0

    def test_rth_not_triggered_when_idle(self, rover: RoverMissionStateMachine):
        triggered = rover.update_battery(BATTERY_RTH_THRESHOLD_PCT - 1.0)
        assert triggered is False  # Not in mission, no RTH needed


class TestCommsTimeout:
    def test_no_timeout_initially(self, rover: RoverMissionStateMachine):
        # Rover is IDLE so comms timeout should not trigger even if stale
        assert rover.check_comms_timeout() is False

    def test_timeout_triggers_when_navigating_and_stale(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        # Force last_comms_at into the past
        rover.last_comms_at = datetime.utcnow() - timedelta(seconds=COMMS_TIMEOUT_SECONDS + 1)
        assert rover.check_comms_timeout() is True

    def test_no_timeout_after_position_update(self, rover: RoverMissionStateMachine):
        _advance_to_navigating(rover)
        rover.update_position(47.6062, -117.3321)
        assert rover.check_comms_timeout() is False

    def test_no_timeout_when_idle(self, rover: RoverMissionStateMachine):
        rover.last_comms_at = datetime.utcnow() - timedelta(seconds=COMMS_TIMEOUT_SECONDS + 60)
        assert rover.check_comms_timeout() is False


class TestMissionAuditLog:
    def test_transition_logged(self, rover: RoverMissionStateMachine):
        rover.transition(MissionState.DISPATCHING, reason="New mission accepted")
        assert len(rover.mission_log) == 1
        entry = rover.mission_log[0]
        assert entry["from_state"] == MissionState.IDLE
        assert entry["to_state"] == MissionState.DISPATCHING
        assert "New mission accepted" in entry["reason"]
        assert "timestamp" in entry

    def test_multiple_transitions_logged(self, rover: RoverMissionStateMachine):
        rover.transition(MissionState.DISPATCHING)
        rover.transition(MissionState.NAVIGATING)
        rover.transition(MissionState.AT_WAYPOINT)
        assert len(rover.mission_log) == 3

    def test_log_has_job_id_when_set(self, rover: RoverMissionStateMachine):
        rover.current_job_id = "job-abc-123"
        rover.transition(MissionState.DISPATCHING)
        assert rover.mission_log[-1]["job_id"] == "job-abc-123"
