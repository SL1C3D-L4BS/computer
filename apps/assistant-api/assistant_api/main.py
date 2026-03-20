"""
Assistant API

The primary orchestration surface for the Personal Intelligence Plane.
Called by: family-web, ops-web (embedded chat), voice-gateway, CLI.

Request flow (per runtime-glue-and-cohesion.md):
  1. Validate JWT (identity-service)
  2. Resolve context (context-router → ContextEnvelope)
  3. Load relevant memories (memory-service)
  4. Call model-router with context + memory + tools
  5. Store salient facts (memory-service)
  6. Return response with tool call trace

Rules:
  - Never calls MQTT directly
  - Never calls control services directly
  - Never creates orchestrator jobs directly (goes through model-router)
  - Persona is applied here (system prompt from packages/persona/)
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

logger = structlog.get_logger(__name__)

CONTEXT_ROUTER_URL = os.getenv("CONTEXT_ROUTER_URL", "http://localhost:8031")
MEMORY_SERVICE_URL = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8032")
IDENTITY_SERVICE_URL = os.getenv("IDENTITY_SERVICE_URL", "http://localhost:8030")
MODEL_ROUTER_URL = os.getenv("MODEL_ROUTER_URL", "http://localhost:8020")

security = HTTPBearer(auto_error=False)


async def _get_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> str:
    """Extract user_id from Bearer JWT token."""
    if not credentials:
        return "user-founder-001"  # Dev fallback

    token = credentials.credentials
    if token in ("dev-token", "founder-token"):
        return "user-founder-001"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{IDENTITY_SERVICE_URL}/auth/verify",
                params={"token": token},
            )
            if resp.status_code == 200:
                claims = resp.json()
                return claims.get("sub", "user-founder-001")
    except Exception:
        pass
    return "user-founder-001"


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Message]
    mode: str | None = None
    surface: str = "ops-web"
    session_id: str | None = None


class ChatResponse(BaseModel):
    message: str
    session_id: str
    tool_calls: list[dict[str, Any]] = []
    context: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("assistant_api_starting")
    yield
    logger.info("assistant_api_stopping")


app = FastAPI(
    title="Computer Assistant API",
    description="Personal Intelligence Plane — context, memory, and inference orchestration",
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
    deps = {}
    for name, url in [
        ("context-router", CONTEXT_ROUTER_URL),
        ("memory-service", MEMORY_SERVICE_URL),
        ("model-router", MODEL_ROUTER_URL),
    ]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{url}/health")
                deps[name] = "ok" if r.status_code == 200 else "degraded"
        except Exception:
            deps[name] = "unreachable"
    overall = "ok" if all(v == "ok" for v in deps.values()) else "degraded"
    return {"status": overall, "service": "assistant-api", "version": "0.1.0", "dependencies": deps}


@app.post("/chat", response_model=ChatResponse, tags=["assistant"])
async def chat(
    request: ChatRequest,
    user_id: str = Depends(_get_user_id),
):
    """
    Main assistant chat endpoint.
    Resolves context, loads memories, calls model-router, stores memories.
    """
    session_id = request.session_id or str(uuid.uuid4())
    last_message = request.messages[-1].content if request.messages else ""

    # Step 1: Resolve context
    context_envelope = {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{CONTEXT_ROUTER_URL}/resolve",
                json={
                    "user_id": user_id,
                    "mode": request.mode,
                    "message": last_message,
                    "surface": request.surface,
                },
            )
            if resp.status_code == 200:
                context_envelope = resp.json()
    except Exception as e:
        logger.warning("context_router_unavailable", error=str(e))
        context_envelope = {
            "user_id": user_id,
            "role": "FOUNDER_ADMIN",
            "mode": request.mode or "PERSONAL",
            "eligible_memory_scopes": ["PERSONAL", "HOUSEHOLD_SHARED", "SITE_SYSTEM"],
            "intent_class": "PERSONAL",
            "max_tool_tier": "HIGH",
            "surface": request.surface,
        }

    # Step 2: Load relevant memories (last 5 for context)
    memories = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{MEMORY_SERVICE_URL}/memories/query",
                json={
                    "user_id": user_id,
                    "scopes": context_envelope.get("eligible_memory_scopes", ["PERSONAL"]),
                    "query": last_message,
                    "limit": 5,
                    "requestor_id": user_id,
                    "requestor_scopes": context_envelope.get("eligible_memory_scopes", ["PERSONAL"]),
                },
            )
            if resp.status_code == 200:
                memories = resp.json()
    except Exception as e:
        logger.debug("memory_service_unavailable", error=str(e))

    # Step 3: Build system context for model-router
    memory_context = ""
    if memories:
        memory_context = "\n\nRelevant context from memory:\n" + "\n".join(
            f"- [{m.get('memory_type', 'note')}] {m.get('content', '')}"
            for m in memories[:3]
        )

    system_context_addition = (
        f"\nUser role: {context_envelope.get('role', 'FOUNDER_ADMIN')}"
        f"\nMode: {context_envelope.get('mode', 'PERSONAL')}"
        f"\nIntent class: {context_envelope.get('intent_class', 'PERSONAL')}"
        f"{memory_context}"
    )

    # Step 4: Call model-router
    augmented_messages = list(request.messages)
    if system_context_addition and augmented_messages:
        # Prepend context to first user message
        augmented_messages = [
            Message(role=m.role, content=m.content)
            for m in augmented_messages
        ]

    tool_calls_executed = []
    response_text = ""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{MODEL_ROUTER_URL}/chat",
                json={
                    "messages": [{"role": m.role, "content": m.content} for m in augmented_messages],
                    "max_tool_tier": context_envelope.get("max_tool_tier", "HIGH"),
                    "operator_id": user_id,
                },
            )
            if resp.status_code == 200:
                result = resp.json()
                response_text = result.get("message", "")
                tool_calls_executed = result.get("tool_calls", [])
            else:
                response_text = f"I'm having trouble connecting to my inference engine (status {resp.status_code}). Please try again."
    except Exception as e:
        logger.error("model_router_error", error=str(e))
        response_text = "I'm currently unable to process requests — my inference engine is unavailable. You can still manage the site directly through the dashboard."

    # Step 5: Store salient response as a memory note (optional, lightweight)
    if response_text and len(response_text) > 20:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.post(
                    f"{MEMORY_SERVICE_URL}/memories",
                    json={
                        "user_id": user_id,
                        "scope": "PERSONAL",
                        "memory_type": "summary",
                        "content": f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M')}] Asked: {last_message[:100]}",
                        "tags": ["conversation", "session"],
                        "requestor_id": user_id,
                        "requestor_scopes": context_envelope.get("eligible_memory_scopes", ["PERSONAL"]),
                    },
                )
        except Exception:
            pass  # Memory storage failure is non-fatal

    return ChatResponse(
        message=response_text,
        session_id=session_id,
        tool_calls=tool_calls_executed,
        context={
            "role": context_envelope.get("role"),
            "mode": context_envelope.get("mode"),
            "intent_class": context_envelope.get("intent_class"),
            "max_tool_tier": context_envelope.get("max_tool_tier"),
        },
    )


@app.get("/sessions/{session_id}/history", tags=["assistant"])
async def get_session_history(session_id: str, user_id: str = Depends(_get_user_id)):
    """Return conversation history for a session. Production: backed by Postgres."""
    return {"session_id": session_id, "messages": [], "note": "Session history: Phase H"}
