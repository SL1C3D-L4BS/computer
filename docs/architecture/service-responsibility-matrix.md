# Service Responsibility Matrix

Every service boundary is hard. These rules are enforced by contract tests and CI.

## Rule: no drift between these services

| Service | Responsibility | What it owns | What it must never do |
|---------|---------------|-------------|----------------------|
| **control-api** | Authenticated external API surface; reads, job submission, approvals, status queries | HTTP routes, auth middleware, request validation | Mutate job state; publish directly to MQTT; call control services |
| **orchestrator** | Internal kernel; policy evaluation, state transitions, command dispatch, audit | Job state machine, policy engine, command log, audit ledger | Expose public HTTP endpoints; accept unauthenticated requests |
| **assistant-api** | Session management, user identity context, conversation endpoints, assistant UX surface | Conversation sessions, session context, user-facing response formatting | Perform model inference; call tool execution directly; touch actuator paths |
| **model-router** | Model selection, tool-call mediation, inference guardrails, structured output validation | Model client lifecycle, tool registry, guardrail rules, structured output schemas | Publish to MQTT; call orchestrator directly; expose product UX |
| **event-ingest** | MQTT consumers, event normalization, canonical event schema writes | MQTT subscriptions, event normalization pipeline, Postgres event writes | Initiate jobs; publish commands; call control services |
| **digital-twin** | Asset registry, entity definitions, capability tags | Asset CRUD, capability resolution, zone definitions | Execute jobs; perform inference; control hardware |
| **context-router** | Resolve user, mode, eligible memory scope, answer/ask/escalate routing | Context envelope (user_id, mode, memory_scope, intent_class) | Perform inference; access hardware; mutate conversation state |
| **memory-service** | Personal and household memory, profiles, preference store | Memory reads/writes, memory scope enforcement, retention policy | Actuate hardware; make inference calls |
| **identity-service** | Household members, roles, permissions, session resolution | User records, role definitions, permission grants | Control hardware; perform inference |

## Enforcement rules

1. **control-api accepts, orchestrator executes.** control-api never mutates job state. Orchestrator never accepts external HTTP without control-api.
2. **assistant-api is product; model-router is infrastructure.** assistant-api calls model-router; model-router does not call back into assistant-api.
3. **AI never touches the actuator path.** model-router → assistant-tools → control-api (for T4 site control). Never model-router → MQTT.
4. **event-ingest is read-only toward hardware.** It normalizes and writes to Postgres. It never publishes commands.
5. **context-router produces a context envelope.** It does not produce a response. Only model-router produces inference output.

## CI enforcement

- Contract tests: each service has an inbound and outbound schema; schema violations fail CI.
- Boundary test: any publish to `computer/+/+/+/command_request` from a non-orchestrator service fails the safety gate.
- AI boundary test: any call from model-router to MQTT fails the AI gate.
