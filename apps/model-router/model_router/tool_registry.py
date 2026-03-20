"""
Tool registry for model-router.

All tools that the AI can use are registered here with explicit:
  - risk_class (maps to orchestrator RiskClass)
  - requires_operator_confirmation (for HIGH/CRITICAL)
  - allowed_origins (AI_ADVISORY only for propose-job tools)

CRITICAL DESIGN RULE (ADR-002):
  - Tools that affect physical systems ONLY submit jobs to orchestrator
  - They NEVER call MQTT, HA, or control services directly
  - The tool_call → orchestrator → policy → approval → execution chain is mandatory

CI Safety Gate (F01) scans this file and all callers to ensure
no tool calls MQTT publish methods directly.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Awaitable

from pydantic import BaseModel

import structlog

logger = structlog.get_logger(__name__)


class ToolRiskClass(str, Enum):
    INFORMATIONAL = "INFORMATIONAL"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ToolDefinition(BaseModel):
    name: str
    description: str
    risk_class: ToolRiskClass
    parameters_schema: dict[str, Any]
    requires_operator_confirmation: bool = False

    class Config:
        arbitrary_types_allowed = True


# ── Tool registry ─────────────────────────────────────────────────────────────
_REGISTRY: dict[str, ToolDefinition] = {}
_HANDLERS: dict[str, Callable[..., Awaitable[Any]]] = {}


def register_tool(definition: ToolDefinition, handler: Callable[..., Awaitable[Any]]) -> None:
    """Register a tool with its definition and async handler."""
    _REGISTRY[definition.name] = definition
    _HANDLERS[definition.name] = handler
    logger.debug("tool_registered", name=definition.name, risk_class=definition.risk_class)


def get_tool(name: str) -> ToolDefinition | None:
    return _REGISTRY.get(name)


def get_all_tools(max_risk_class: ToolRiskClass | None = None) -> list[ToolDefinition]:
    """Return all registered tools, optionally filtered by max risk class."""
    risk_order = [
        ToolRiskClass.INFORMATIONAL,
        ToolRiskClass.LOW,
        ToolRiskClass.MEDIUM,
        ToolRiskClass.HIGH,
    ]
    tools = list(_REGISTRY.values())
    if max_risk_class:
        max_idx = risk_order.index(max_risk_class)
        tools = [t for t in tools if risk_order.index(t.risk_class) <= max_idx]
    return tools


def get_openai_tool_schemas(max_risk_class: ToolRiskClass | None = None) -> list[dict]:
    """Return OpenAI-compatible tool schemas for chat completions."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters_schema,
            },
        }
        for t in get_all_tools(max_risk_class)
    ]


async def execute_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a registered tool. Returns result dict."""
    handler = _HANDLERS.get(name)
    if not handler:
        return {"error": f"Tool '{name}' not found in registry"}
    try:
        result = await handler(**arguments)
        logger.info("tool_executed", tool=name)
        return result if isinstance(result, dict) else {"result": result}
    except Exception as e:
        logger.error("tool_execution_failed", tool=name, error=str(e))
        return {"error": str(e)}
