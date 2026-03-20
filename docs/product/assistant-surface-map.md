# Assistant Surface Map

Maps each assistant UX surface to its backing service, session model, and intent routing behavior.

## Surfaces overview

| Surface | Type | Primary users | Backed by | Session model |
|---------|------|-------------|-----------|--------------|
| **voice-gateway** | Real-time audio | All household members | assistant-api | Stateful session per wakeword activation |
| **family-web** | Web/mobile app | All household members | assistant-api | Auth session per user |
| **chat (ops-web embedded)** | Web chat | Founder/Admin | assistant-api (work/site mode) | Auth session, mode=WORK or SITE |
| **CLI** | Terminal | Founder/Admin | assistant-api | Short-lived session; no memory write |

## Surface → service flow

```
voice-gateway ─┐
family-web     ├──► assistant-api ──► context-router ──► model-router
chat (ops)     ┘         │
                    (session mgmt,         (user,        (inference,
                     input routing)         mode,         tools,
                                        memory_scope,   guardrails)
                                         intent_class)
```

## Voice gateway (services/voice-gateway/)

- **Wake word**: Porcupine (local, on Pi 5)
- **STT**: Whisper (local, on Pi 5 or edge GPU)
- **TTS**: Piper (local)
- **Protocol to assistant-api**: WebSocket audio session → text input/output
- **Session lifecycle**: wakeword detected → open session → STT → assistant-api → TTS → close session
- **Mode resolution**: voice-gateway passes device_id; context-router resolves mode from device location and time of day
- **Degraded behavior**: if assistant-api is down, TTS responds "I'm unavailable right now" and logs the attempt

## Family web (apps/family-web/)

- **Framework**: Next.js (same version as ops-web; shared UI package)
- **Auth**: identity-service (household login; role-aware)
- **Surfaces**: reminders, chores, shopping list, shared calendar, household notes, approvals queue, conversation history
- **Mode**: defaults to FAMILY mode; adults can switch to PERSONAL
- **Real-time**: WebSocket from assistant-api for streaming responses
- **Approvals queue**: shows pending high-risk jobs from orchestrator (sourced via control-api); allows approve/reject

## Chat (embedded in ops-web)

- **Mode**: WORK or SITE depending on context
- **Users**: FOUNDER_ADMIN only
- **Memory scope**: project context (work mode) or site/system (site mode)
- **Not a general assistant**: purpose-built for coding help, architecture memory, runbook lookup, job inspection

## Intent routing per surface

Context-router classifies every input into one of four intent classes before tool execution:

| Intent class | Example | Execution path |
|-------------|---------|---------------|
| `PERSONAL` | "Remind me to call mom tomorrow" | assistant-tools only (T3) |
| `HOUSEHOLD` | "What's for dinner this week?" | family memory / routine-engine |
| `SITE_OPS` | "Show greenhouse humidity zone A" | control-api read-only query (T3) |
| `HIGH_RISK_CONTROL` | "Open north irrigation valve" | job proposal → approval → orchestrator (T4) |

The intent class is resolved by context-router before model-router is called. model-router uses it to constrain tool access.

## Operating modes per surface

| Mode | Available on | Memory scope | Tool tier limit |
|------|-------------|-------------|----------------|
| PERSONAL | voice, family-web, chat | Personal only | T3 |
| FAMILY | voice, family-web | Household shared | T3 |
| WORK | chat, family-web | Project context | T3 + research tools |
| SITE | chat (ops-web), voice | Site/system | T4 (with approval) |
| EMERGENCY | voice, ops-web | Site/system | T4 restricted; see emergency-mode-spec |

## Non-surfaces (explicitly excluded)

- assistant-api must not be exposed as a generic REST API callable by arbitrary clients.
- MQTT is not an assistant surface.
- model-router is not a public surface; it is infrastructure.
- ops-web job console is an ops surface, not an assistant surface.
