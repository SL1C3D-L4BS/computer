"""Tests for greenhouse zone state machine."""
import pytest
from greenhouse_control.state_machine import ZoneState, ZoneStateMachine


@pytest.fixture
def zone():
    return ZoneStateMachine("greenhouse-north")


def test_initial_state_is_idle(zone):
    assert zone.state == ZoneState.IDLE


def test_idle_to_monitoring(zone):
    zone.transition(ZoneState.MONITORING)
    assert zone.state == ZoneState.MONITORING


def test_monitoring_to_heating(zone):
    zone.transition(ZoneState.MONITORING)
    zone.transition(ZoneState.HEATING)
    assert zone.state == ZoneState.HEATING


def test_invalid_idle_to_heating_raises(zone):
    with pytest.raises(ValueError):
        zone.transition(ZoneState.HEATING)


def test_e_stop_from_any_state(zone):
    zone.transition(ZoneState.MONITORING)
    zone.transition(ZoneState.HEATING)
    zone.e_stop("Test E-stop")
    assert zone.state == ZoneState.SAFE_HOLD


def test_clear_safe_hold_returns_to_idle(zone):
    zone.transition(ZoneState.MONITORING)
    zone.e_stop("Test E-stop")
    zone.clear_safe_hold()
    assert zone.state == ZoneState.IDLE


def test_cannot_clear_safe_hold_from_non_safe_hold(zone):
    with pytest.raises(ValueError):
        zone.clear_safe_hold()


def test_frost_risk_detected_below_threshold(zone):
    zone.update_reading({"temperature_celsius": 1.5})
    assert zone.evaluate_frost_risk(2.0) is True


def test_frost_risk_not_detected_above_threshold(zone):
    zone.update_reading({"temperature_celsius": 5.0})
    assert zone.evaluate_frost_risk(2.0) is False


def test_frost_risk_no_reading(zone):
    assert zone.evaluate_frost_risk(2.0) is False


def test_overheating_detected_above_threshold(zone):
    zone.update_reading({"temperature_celsius": 38.0})
    assert zone.evaluate_overheating_risk(35.0) is True


def test_mutually_exclusive_states(zone):
    """Heater and vent cannot be active simultaneously — must go via MONITORING."""
    zone.transition(ZoneState.MONITORING)
    zone.transition(ZoneState.HEATING)
    # Cannot go directly from HEATING to VENTILATING
    with pytest.raises(ValueError):
        zone.transition(ZoneState.VENTILATING)
    # Must go back through MONITORING
    zone.transition(ZoneState.MONITORING)
    zone.transition(ZoneState.VENTILATING)
    assert zone.state == ZoneState.VENTILATING
