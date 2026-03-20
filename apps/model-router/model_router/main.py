"""
Model Router Service

Responsibilities:
  - Route inference requests to appropriate LLM backend (Ollama, vLLM)
  - Execute tool calls with registered tools (INFORMATIONAL through HIGH risk)
  - Propose jobs to orchestrator via AI_ADVISORY origin
  - Enforce tool tier limits from context-router ContextEnvelope
  - Stream operator copilot responses

MUST NOT (ADR-002):
  - Publish to MQTT directly (CI F01 gate)
  - Call HA, control services, or adapters directly
  - Auto-approve any orchestrator job
  - Store conversation memory (assistant-api handles this)
"""
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Import tools to register them
from .tool_registry import (
    ToolRiskClass,
    execute_tool,
    get_all_tools,
    get_openai_tool_schemas,
)
import model_router.tools  # noqa: F401 — registers all tools on import

logger = structlog.get_logger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.3:70b-instruct-q4_K_M")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # Optional: for OpenAI fallback

# System prompt for operator copilot mode
OPERATOR_COPILOT_SYSTEM_PROMPT = """You are Computer, an intelligent assistant for a cyber-physical homestead.
You help the operator manage greenhouse climate, hydroponics, energy, security, and irrigation.

Key rules:
- You INFORM and ADVISE; you never directly control physical systems
- When you want to propose an action, use the available tools to submit job proposals
- All HIGH-risk actions require operator approval before execution
- Be precise, concise, and actionable in your responses
- When sensors show anomalies, explain what you see and what you recommend

Available capabilities: read sensor data, list assets, propose irrigation, read specific sensors.
If a request requires capabilities you don't have (drone, rover, chemicals), say so clearly."""


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("model_router_starting", model=OLLAMA_MODEL, ollama_url=OLLAMA_URL)
    # Verify Ollama connectivity (optional — service may start before Ollama)
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                logger.info("ollama_connected", available_models=models)
    except Exception:
        logger.warning("ollama_not_available_at_startup")
    yield


app = FastAPI(
    title="Model Router",
    description="AI inference routing, tool execution, and operator copilot",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health():
    ollama_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_URL}/api/tags")
            ollama_status = "ok" if resp.status_code == 200 else "down"
    except Exception:
        ollama_status = "unreachable"
    return {
        "status": "ok" if ollama_status == "ok" else "degraded",
        "service": "model-router",
        "version": "0.1.0",
        "ollama": ollama_status,
        "registered_tools": len(get_all_tools()),
    }


@app.get("/tools", tags=["tools"])
async def list_tools(max_risk: str | None = None):
    """List available tools, optionally filtered by max risk class."""
    max_risk_class = ToolRiskClass(max_risk.upper()) if max_risk else None
    return [t.model_dump() for t in get_all_tools(max_risk_class)]


class ChatMessage(BaseModel):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str


class CopilotRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    max_tool_tier: str = "HIGH"  # From ContextEnvelope
    operator_id: str | None = None
    stream: bool = False


class ToolCallResult(BaseModel):
    tool_name: str
    arguments: dict
    result: dict


class CopilotResponse(BaseModel):
    message: str
    tool_calls: list[ToolCallResult] = []
    model_used: str
    tokens_used: int | None = None


@app.post("/chat", response_model=CopilotResponse, tags=["inference"])
async def chat(request: CopilotRequest):
    """
    Operator copilot chat endpoint.
    Routes to Ollama, executes tool calls with policy enforcement.
    """
    model = request.model or OLLAMA_MODEL
    max_risk_class = ToolRiskClass(request.max_tool_tier)
    tools = get_openai_tool_schemas(max_risk_class)

    messages = [
        {"role": "system", "content": OPERATOR_COPILOT_SYSTEM_PROMPT},
        *[{"role": m.role, "content": m.content} for m in request.messages],
    ]

    tool_calls_executed: list[ToolCallResult] = []

    # Agentic loop: model → tool calls → model → ...
    max_iterations = 5
    for iteration in range(max_iterations):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False,
                }
                if tools:
                    payload["tools"] = tools

                resp = await client.post(
                    f"{OLLAMA_URL}/api/chat",
                    json=payload,
                )

                if resp.status_code != 200:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Ollama returned {resp.status_code}: {resp.text[:200]}",
                    )

                result = resp.json()
                msg = result.get("message", {})

                # No tool calls — final response
                if not msg.get("tool_calls"):
                    return CopilotResponse(
                        message=msg.get("content", ""),
                        tool_calls=tool_calls_executed,
                        model_used=model,
                        tokens_used=result.get("eval_count"),
                    )

                # Execute tool calls
                messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": msg["tool_calls"]})

                for tool_call in msg["tool_calls"]:
                    fn = tool_call.get("function", {})
                    tool_name = fn.get("name")
                    arguments = fn.get("arguments", {})
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except Exception:
                            arguments = {}

                    # Enforce tool tier limit
                    tool_def = __import__("model_router.tool_registry", fromlist=["get_tool"]).get_tool(tool_name)
                    if tool_def:
                        tool_risk_order = ["INFORMATIONAL", "LOW", "MEDIUM", "HIGH"]
                        if tool_risk_order.index(tool_def.risk_class) > tool_risk_order.index(max_risk_class):
                            tool_result = {"error": f"Tool {tool_name} risk class {tool_def.risk_class} exceeds max allowed {max_risk_class}"}
                        else:
                            tool_result = await execute_tool(tool_name, arguments)
                    else:
                        tool_result = {"error": f"Tool {tool_name} not found"}

                    tool_calls_executed.append(ToolCallResult(
                        tool_name=tool_name,
                        arguments=arguments,
                        result=tool_result,
                    ))

                    messages.append({
                        "role": "tool",
                        "content": json.dumps(tool_result),
                    })

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Inference error: {str(e)}")

    return CopilotResponse(
        message="Maximum tool call iterations reached.",
        tool_calls=tool_calls_executed,
        model_used=model,
    )


class ProposeJobRequest(BaseModel):
    job_type: str
    target_asset_ids: list[str]
    risk_class: str
    parameters: dict = {}
    reason: str
    requested_by: str = "model-router"


@app.post("/propose-job", tags=["jobs"])
async def propose_job(request: ProposeJobRequest):
    """
    Propose a job to the orchestrator from AI advisory context.
    All jobs submitted here use origin=AI_ADVISORY.
    HIGH/CRITICAL risk jobs will require OPERATOR_REQUIRED approval.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{os.getenv('ORCHESTRATOR_URL', 'http://localhost:8002')}/jobs",
                json={
                    "type": request.job_type,
                    "origin": "AI_ADVISORY",
                    "target_asset_ids": request.target_asset_ids,
                    "risk_class": request.risk_class,
                    "parameters": {**request.parameters, "ai_reason": request.reason},
                    "requested_by": request.requested_by,
                },
                timeout=10.0,
            )
            if resp.status_code in (200, 201):
                job = resp.json()
                logger.info(
                    "job_proposed_via_model_router",
                    job_id=job["job_id"],
                    state=job["state"],
                    approval_mode=job["approval_mode"],
                )
                return {
                    "job_id": job["job_id"],
                    "state": job["state"],
                    "approval_mode": job["approval_mode"],
                    "pending_approval": job["state"] == "VALIDATING",
                }
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Orchestrator unavailable: {e}")
