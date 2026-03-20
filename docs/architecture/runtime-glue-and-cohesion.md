# Runtime Glue and System Cohesion

This document specifies the flows, startup order, identity propagation, and health model that turn Computer from a pile of components into one cohesive system.

## 1. Request and command flow (ops plane)

```
ops-web ──HTTP/WS──► control-api ──HTTP/RPC──► orchestrator
                         │                          │
                    (auth, validate)          (policy, state-machine,
                    (no state mutation)        audit, dispatch)
                                                    │
                                     ┌──────────────┤
                                     │              │
                              MQTT cmd-req    service call
                                     │              │
                           greenhouse-control  hydro-control
                           rover-control       drone-control
                                     │
                              L0 devices (MCU, relay, pump)
                                     │
                              MQTT cmd-ack ──► orchestrator ──► Postgres audit
```

Rules:
- **control-api** validates auth, rate-limits, and deserializes. It then calls orchestrator. It never mutates job state.
- **orchestrator** is the only writer of job state. It evaluates policy, advances state machine, dispatches commands, and writes audit.
- **Control services** (greenhouse-control, hydro-control, rover-control, drone-control) receive command-request from orchestrator, validate again locally, publish to L0 device topics, and send command-ack.
- **ops-web** polls or subscribes via control-api WebSocket for live status. It never calls orchestrator directly.

## 2. Request and context flow (assistant plane)

```
voice-gateway ─┐
family-web     ├──HTTP──► assistant-api ──► context-router
chat client ───┘                │               │
                          (session, raw      (user_id, mode,
                           input only)        memory_scope,
                                             intent_class)
                                │
                                ▼
                          model-router ──► inference (Ollama/vLLM)
                                │
                    ┌───────────┼───────────┐
                    │           │           │
             memory-service  identity   assistant-tools
                                              │
                                     (for site control: T4)
                                              │
                                         control-api ──► orchestrator
```

Rules:
- **assistant-api** receives session input and outputs formatted responses. It calls context-router and model-router; it does not perform inference or tool execution itself.
- **context-router** resolves user identity (via identity-service), operating mode, eligible memory scope, and intent class. Returns a context envelope; does not produce a response.
- **model-router** receives the context envelope, selects model, mediates tool calls with guardrails, validates structured outputs. It calls assistant-tools within policy tier limits.
- **assistant-tools** calls control-api (never MQTT directly) for T4 site control actions. For T3 and below, tools access memory-service, identity-service, or external APIs.
- The assistant plane never publishes to MQTT command topics.

## 3. Event and job flow (kernel)

```
L0 devices / HA / Frigate
       │
   MQTT telemetry/event topics
       │
   event-ingest ──► normalize ──► Postgres (events table)
                                       │
                               orchestrator (sensor_rule origin)
                                       │
                               Job: PENDING → VALIDATING
                                       │
                           command-policy evaluation
                                       │
                      ┌────────────────┤
                      │                │
                 APPROVED          REJECTED
                      │                │
               EXECUTING         audit + notify
                      │
              control service dispatch
                      │
               command-ack / state update
                      │
               orchestrator: COMPLETED | FAILED | ABORTED
                      │
               Postgres audit (full command_log)
```

Every job carries: `job_id`, `request_id`, `origin`, `requested_by`, `target_asset_ids`, `risk_class`, `approval_mode`, `state`, `command_log[]`, `telemetry_refs[]`, `abort_conditions`.

## 4. Startup and dependency order

Bootstrap must start services in this order and verify health at each tier before proceeding.

| Tier | Services | Dependencies | Health check |
|------|---------|-------------|-------------|
| **1 Infrastructure** | Postgres, Redis, Mosquitto (MQTT) | None | TCP connect + ping |
| **2 Kernel** | digital-twin, orchestrator | Postgres, Redis, MQTT | `/health` HTTP 200 |
| **3 API and ingest** | control-api, event-ingest | orchestrator, MQTT, Postgres | `/health` HTTP 200 |
| **4 Adapters and control services** | ha-adapter, frigate-adapter, greenhouse-control, hydro-control, energy-engine | MQTT, optionally control-api | MQTT connect + `/health` |
| **5 Assistant plane** | identity-service, memory-service, context-router, model-router, assistant-api | Postgres, Redis, optionally MQTT | `/health` HTTP 200 |
| **6 UX** | ops-web, family-web, voice-gateway | control-api, assistant-api | HTTP 200 root |

`./bootstrap.sh` enforces this order with health polling at each tier boundary. Never skip tiers.

## 5. Identity and correlation

Every request carries a `request_id` (UUID v4). It is:
- Generated at the boundary (control-api for ops; assistant-api for assistant).
- Propagated through all internal calls as an HTTP header (`X-Request-ID`) and in MQTT payloads (`request_id` field).
- Stored on the Job record (`request_id` column).
- Written to every audit event and command_log entry.

Session and user identity:
- assistant-api resolves session → user via identity-service.
- context-router receives `user_id` and `mode`; returns `memory_scope` and `intent_class`.
- model-router and tools use `user_id`, `mode`, `memory_scope` from the context envelope.
- Ops requests carry `operator_id` from control-api JWT auth.

Trace: `request_id` → `job_id` → `command_log` → `telemetry_refs`. One trace from "user asked" to "command executed" to "audit written."

## 6. Health and liveness

Every service exposes:
- `GET /health` → `{"status": "ok" | "degraded" | "down", "dependencies": {...}}`
- `GET /ready` → `{"ready": true | false}` (optional; for orchestration use)

Bootstrap glue polls `/health` at each tier boundary. If any service returns `degraded` or `down`, bootstrap halts and reports which tier failed.

In production, a minimal supervisor (compose healthchecks or a glue process) continuously checks tier health and exposes a single system health endpoint.

Degraded behavior per service: defined in `docs/safety/degraded-mode-spec.md`. The glue layer does not hide partial failure; it surfaces which component is unhealthy to the operator.

## 7. Deliverables

| File | Purpose |
|------|---------|
| `docs/architecture/runtime-glue-and-cohesion.md` | This document |
| `docs/delivery/bootstrap-boundaries.md` | What bootstrap brings up, dependency order |
| `./bootstrap.sh` | Executable bring-up enforcing this order |
| `packages/sdk/` | Shared request_id propagation middleware |
| `apps/*/health.py` or `apps/*/src/health.ts` | Per-service health endpoints |
