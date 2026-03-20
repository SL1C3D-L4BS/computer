"""
Milestone 4 Integration Tests
Definition of Done:
  - AI recommends actions via propose-job endpoint
  - AI_ADVISORY HIGH-risk jobs require operator approval (F05)
  - AI_ADVISORY LOW-risk jobs are auto-approved
  - Tool registry enforces risk tier limits
  - Model-router never publishes to MQTT command topics (F01)

These tests verify the AI advisory layer without requiring Ollama to be running.
"""
import os

import httpx
import pytest

MODEL_ROUTER = os.getenv("MODEL_ROUTER_URL", "http://localhost:8020")
ORCHESTRATOR = os.getenv("ORCHESTRATOR_URL", "http://localhost:8002")


def _service_available(url: str) -> bool:
    try:
        r = httpx.get(f"{url}/health", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


class TestAIAdvisoryFlow:
    def test_propose_job_endpoint_requires_operator_for_high_risk(self):
        """
        AI-proposed HIGH-risk job must be in VALIDATING state — never auto-approved (F05).
        """
        if not _service_available(MODEL_ROUTER):
            pytest.skip("model-router not running")
        if not _service_available(ORCHESTRATOR):
            pytest.skip("orchestrator not running")

        r = httpx.post(
            f"{MODEL_ROUTER}/propose-job",
            json={
                "job_type": "irrigation.zone.enable",
                "target_asset_ids": ["asset:actuator:valve:irrigation:zone-1"],
                "risk_class": "HIGH",
                "parameters": {"zone_id": "zone-1", "duration_minutes": 30},
                "reason": "Soil moisture below 30% VWC threshold",
            },
            timeout=15,
        )
        assert r.status_code == 200
        result = r.json()
        assert result["state"] == "VALIDATING", (
            f"AI_ADVISORY HIGH-risk job must be VALIDATING, got: {result['state']}"
        )
        assert result["pending_approval"] is True
        assert result["approval_mode"] in ("OPERATOR_REQUIRED", "OPERATOR_CONFIRM_TWICE")

    def test_propose_job_low_risk_auto_approved(self):
        """AI-proposed LOW-risk sensor read is auto-approved."""
        if not _service_available(MODEL_ROUTER):
            pytest.skip("model-router not running")

        r = httpx.post(
            f"{MODEL_ROUTER}/propose-job",
            json={
                "job_type": "sensor.read",
                "target_asset_ids": ["asset:sensor:temp:greenhouse-north"],
                "risk_class": "LOW",
                "parameters": {"reading_type": "temperature"},
                "reason": "Checking frost risk before night",
            },
            timeout=10,
        )
        assert r.status_code == 200
        result = r.json()
        # AI_ADVISORY + LOW = AUTO_WITH_AUDIT (auto-approved)
        assert result["state"] in ("APPROVED", "EXECUTING", "COMPLETED"), (
            f"AI_ADVISORY LOW-risk job should be auto-approved, got: {result['state']}"
        )
        assert result.get("pending_approval") is not True


class TestToolRegistry:
    def test_tools_endpoint_returns_registered_tools(self):
        """Model-router exposes its tool registry."""
        if not _service_available(MODEL_ROUTER):
            pytest.skip("model-router not running")

        r = httpx.get(f"{MODEL_ROUTER}/tools", timeout=5)
        assert r.status_code == 200
        tools = r.json()
        assert len(tools) >= 3

    def test_high_risk_tools_filtered_at_medium_max(self):
        """When max_risk=medium, HIGH-risk tools are not returned."""
        if not _service_available(MODEL_ROUTER):
            pytest.skip("model-router not running")

        r = httpx.get(f"{MODEL_ROUTER}/tools", params={"max_risk": "medium"}, timeout=5)
        assert r.status_code == 200
        tools = r.json()
        for tool in tools:
            assert tool["risk_class"] not in ("HIGH", "CRITICAL"), (
                f"Tool {tool['name']} with risk {tool['risk_class']} should not appear at MEDIUM max"
            )

    def test_informational_tools_always_available(self):
        """INFORMATIONAL tools appear at every risk tier."""
        if not _service_available(MODEL_ROUTER):
            pytest.skip("model-router not running")

        r = httpx.get(f"{MODEL_ROUTER}/tools", params={"max_risk": "informational"}, timeout=5)
        assert r.status_code == 200
        tools = r.json()
        assert any(t["risk_class"] == "INFORMATIONAL" for t in tools)


class TestAISafetyBoundaries:
    def test_model_router_health_ok(self):
        """Model-router service should be healthy."""
        if not _service_available(MODEL_ROUTER):
            pytest.skip("model-router not running")

        r = httpx.get(f"{MODEL_ROUTER}/health", timeout=5)
        assert r.status_code == 200
        health = r.json()
        assert health["service"] == "model-router"

    def test_no_direct_mqtt_publish_in_source(self):
        """
        F01 architectural check: verify model-router tools source
        does not contain direct MQTT command publishes.
        """
        import inspect
        from model_router import tools
        source = inspect.getsource(tools)
        forbidden = [
            'client.publish(f"commands/',
            'client.publish("commands/',
        ]
        for pattern in forbidden:
            assert pattern not in source, (
                f"F01 VIOLATION: Model-router contains forbidden MQTT publish pattern: '{pattern}'"
            )
