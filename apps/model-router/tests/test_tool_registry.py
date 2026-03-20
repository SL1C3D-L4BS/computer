"""Tests for tool registry — ensures AI boundary safety."""
import pytest
from model_router.tool_registry import (
    ToolDefinition,
    ToolRiskClass,
    get_all_tools,
    get_openai_tool_schemas,
    register_tool,
)
import model_router.tools  # noqa: F401 — registers all tools


def test_tools_are_registered():
    """At minimum, core tools should be registered."""
    tools = get_all_tools()
    assert len(tools) >= 3, "Expected at least 3 tools registered"


def test_informational_tools_available_at_all_tiers():
    """INFORMATIONAL tools must be available at every risk tier."""
    for tier in ToolRiskClass:
        tools = get_all_tools(max_risk_class=tier)
        assert any(t.risk_class == ToolRiskClass.INFORMATIONAL for t in tools), (
            f"No INFORMATIONAL tools available at tier {tier}"
        )


def test_high_risk_tools_filtered_at_medium_tier():
    """HIGH risk tools must not appear when max_risk_class=MEDIUM."""
    tools = get_all_tools(max_risk_class=ToolRiskClass.MEDIUM)
    for tool in tools:
        assert tool.risk_class != ToolRiskClass.HIGH, (
            f"HIGH risk tool {tool.name} should not appear at MEDIUM max tier"
        )


def test_high_risk_tool_requires_operator_confirmation():
    """Any registered HIGH risk tool must have requires_operator_confirmation=True."""
    high_risk_tools = [t for t in get_all_tools() if t.risk_class == ToolRiskClass.HIGH]
    for tool in high_risk_tools:
        assert tool.requires_operator_confirmation, (
            f"HIGH risk tool {tool.name} must have requires_operator_confirmation=True"
        )


def test_openai_tool_schemas_are_valid():
    """OpenAI tool schemas must be well-formed."""
    schemas = get_openai_tool_schemas()
    for schema in schemas:
        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "description" in schema["function"]
        assert "parameters" in schema["function"]


def test_no_mqtt_publish_in_tools_module():
    """
    CI Safety Gate F01 check: model_router.tools must not contain
    direct MQTT publish calls.
    """
    import inspect
    import model_router.tools as tools_module
    source = inspect.getsource(tools_module)
    # Check for direct MQTT publish patterns
    forbidden_patterns = [
        "client.publish(f\"commands/",
        "client.publish(\"commands/",
        "mqtt_client.publish",
        'await client.publish("command',
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source, (
            f"F01 VIOLATION: Found forbidden MQTT publish pattern in tools.py: '{pattern}'"
        )
