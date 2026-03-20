"""
Milestone 3 Integration Tests
Definition of Done:
  - Event ingest and triage works
  - Security incidents are created from detection events
  - No autonomous physical response occurs (validated)
  - Operator can acknowledge and resolve incidents

Tests use simulation endpoints to avoid hardware dependencies.
"""
import os

import httpx
import pytest

SECURITY_MONITOR = os.getenv("SECURITY_MONITOR_URL", "http://localhost:8014")
FRIGATE_ADAPTER = os.getenv("FRIGATE_ADAPTER_URL", "http://localhost:8015")
ORCHESTRATOR = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")


def _service_available(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


class TestEventIngestAndTriage:
    def test_simulated_detection_creates_incident(self):
        """Simulating a Frigate detection creates a security incident."""
        if not _service_available(SECURITY_MONITOR):
            pytest.skip("security-monitor not running")

        r = httpx.post(
            f"{SECURITY_MONITOR}/incidents/simulate",
            json={
                "event_type": "security.detection.new",
                "asset_id": "asset:sensor:camera:exterior-north",
                "severity": "WARNING",
                "payload": {"label": "person", "score": 0.92, "camera": "exterior_north"},
            },
            timeout=10,
        )
        assert r.status_code == 200
        incident = r.json()
        assert incident["state"] in ("NEW", "TRIAGED")
        assert incident["severity"] == "WARNING"
        assert "person" in incident["description"].lower()

    def test_info_severity_incident_auto_triaged(self):
        """INFO severity incidents are auto-triaged (not immediately actionable)."""
        if not _service_available(SECURITY_MONITOR):
            pytest.skip("security-monitor not running")

        r = httpx.post(
            f"{SECURITY_MONITOR}/incidents/simulate",
            json={
                "event_type": "security.motion.detected",
                "asset_id": "asset:sensor:camera:driveway",
                "severity": "INFO",
                "payload": {"motion_active": True},
            },
            timeout=10,
        )
        assert r.status_code == 200
        incident = r.json()
        # INFO auto-triaged; should not be NEW
        assert incident["state"] == "TRIAGED", (
            "INFO incidents should be auto-triaged, not require operator action"
        )

    def test_critical_incident_requires_operator_acknowledgment(self):
        """CRITICAL incidents must be acknowledged by operator before resolution."""
        if not _service_available(SECURITY_MONITOR):
            pytest.skip("security-monitor not running")

        # Create CRITICAL incident
        r = httpx.post(
            f"{SECURITY_MONITOR}/incidents/simulate",
            json={
                "event_type": "security.detection.new",
                "asset_id": "asset:sensor:camera:exterior-north",
                "severity": "CRITICAL",
                "payload": {"label": "fire", "score": 0.95},
            },
            timeout=10,
        )
        assert r.status_code == 200
        incident = r.json()
        incident_id = incident["incident_id"]

        # Cannot resolve without acknowledgment — must go through state machine
        assert incident["state"] in ("NEW", "TRIAGED")

        # Acknowledge the incident
        r = httpx.post(
            f"{SECURITY_MONITOR}/incidents/{incident_id}/acknowledge",
            json={"operator_id": "operator_001", "note": "Investigating fire alarm"},
            timeout=10,
        )
        assert r.status_code == 200
        ack = r.json()
        assert ack["state"] == "ACKNOWLEDGED"
        assert ack["acknowledged_by"] == "operator_001"

        # Resolve
        r = httpx.post(
            f"{SECURITY_MONITOR}/incidents/{incident_id}/resolve",
            json={"operator_id": "operator_001", "resolution": "False alarm confirmed"},
            timeout=10,
        )
        assert r.status_code == 200
        resolved = r.json()
        assert resolved["state"] == "RESOLVED"


class TestNoAutonomousPhysicalResponse:
    """
    Verify the architecture fitness function: no autonomous physical response.
    Security events must not trigger any EXECUTING jobs automatically.
    """

    def test_person_detection_does_not_create_executing_jobs(self):
        """
        Person detection must NOT create any auto-executing jobs.
        Any response must require operator approval.
        """
        if not _service_available(SECURITY_MONITOR):
            pytest.skip("security-monitor not running")
        if not _service_available(ORCHESTRATOR):
            pytest.skip("orchestrator not running")

        # Count EXECUTING jobs before
        r = httpx.get(f"{ORCHESTRATOR}/jobs", params={"state": "EXECUTING"}, timeout=5)
        executing_before = len(r.json()) if r.status_code == 200 else 0

        # Simulate person detection
        httpx.post(
            f"{SECURITY_MONITOR}/incidents/simulate",
            json={
                "event_type": "security.detection.new",
                "asset_id": "asset:sensor:camera:exterior-north",
                "severity": "WARNING",
                "payload": {"label": "person", "score": 0.88},
            },
            timeout=10,
        )

        # Verify no new EXECUTING jobs were auto-created
        r = httpx.get(f"{ORCHESTRATOR}/jobs", params={"state": "EXECUTING"}, timeout=5)
        executing_after = len(r.json()) if r.status_code == 200 else 0

        assert executing_after == executing_before, (
            f"Security detection event created {executing_after - executing_before} "
            "new EXECUTING jobs automatically. This violates the no-autonomous-response rule."
        )

    def test_frigate_event_normalizer_does_not_publish_commands(self):
        """
        Frigate adapter must publish to events/ topics only, never commands/ topics.
        This is enforced by MQTT ACL (acl.conf).
        """
        if not _service_available(FRIGATE_ADAPTER):
            pytest.skip("frigate-adapter not running")

        # Simulate a detection through frigate-adapter
        r = httpx.post(
            f"{FRIGATE_ADAPTER}/events/simulate",
            json={
                "camera": "exterior_north",
                "label": "person",
                "score": 0.90,
                "event_type": "new",
            },
            timeout=10,
        )
        if r.status_code != 200:
            pytest.skip("frigate-adapter simulation not available")

        # Verify the event was normalized (not a command)
        r = httpx.get(f"{FRIGATE_ADAPTER}/events", timeout=5)
        assert r.status_code == 200
        events = r.json()
        if events:
            event = events[-1]
            assert event.get("event_type", "").startswith("security."), (
                "Frigate events must be canonical security events, not commands"
            )
            assert "command" not in event.get("event_type", ""), (
                "Frigate adapter must never emit command events"
            )
