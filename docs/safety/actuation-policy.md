# Actuation Policy

Defines the rules for all physical actuation in the Computer system. Violations are caught by CI safety gates.

## Core rule (non-negotiable)

**No service other than orchestrator may publish to MQTT command_request topics or directly actuate hardware.**

The only permitted actuation path is:

```
Orchestrator → control service → L0 device
```

Everything else (control-api, event-ingest, model-router, assistant-tools, adapters) must route through orchestrator or a control service.

## Permitted actuation sources

| Source | May actuate? | Mechanism |
|--------|------------|-----------|
| orchestrator | Yes, indirect | Dispatches to control services via MQTT command_request or HTTP |
| greenhouse-control | Yes, within policy | Receives from orchestrator; publishes to L0 device topics |
| hydro-control | Yes, within policy | Receives from orchestrator; publishes to L0 device topics |
| energy-engine | Yes, within policy | Receives from orchestrator; manages relay/BMS through policy |
| rover-control | Yes, within policy | Receives mission from orchestrator; ROS2 Nav2 bridge |
| drone-control | Yes, within policy | Receives mission from orchestrator; PX4 bridge |
| HA automation | Yes, limited | Only for pre-approved automations; never as control plane |
| Emergency mode | Yes, bounded | Emergency actions only; see emergency-mode-spec.md |

## Forbidden actuation sources

| Source | Reason |
|--------|--------|
| model-router | AI advisory only; never actuates |
| assistant-tools | Submits job proposals to control-api only |
| event-ingest | Read/write to DB only; no commands |
| frigate-adapter | Event normalization only; no commands |
| ha-adapter | Entity sync only; no commands from this path |
| ops-web | UI only; submits via control-api |
| family-web | UI only; no site control in family mode |
| voice-gateway | Interface only; routes to assistant-api |

## Pre-actuation checks (orchestrator enforces)

Before any job transitions from APPROVED → EXECUTING, orchestrator must verify:

1. **Asset preconditions**: All `preconditions` on the job are satisfied.
2. **Safety interlocks**: No conflicting job is in EXECUTING state for the same asset.
3. **Risk class approval**: Job has a logged approval event matching its `approval_mode`.
4. **Abort conditions evaluated**: `abort_conditions` are not currently true.
5. **Control service reachable**: Target control service returns a health check 200.

If any check fails, job transitions to FAILED with logged reason. It does not silently proceed.

## Post-actuation requirements

After dispatching a command, orchestrator must:

1. Log the dispatch in `command_log` with timestamp and target.
2. Subscribe to `command-ack` topic (or poll) within the defined timeout.
3. If ack not received within timeout: retry once, then transition job to FAILED.
4. On success: transition to COMPLETED and log outcome.
5. Write an audit event to Postgres regardless of outcome.

## Device-level actuation rules

L0 devices (MCUs, relays, pumps):
- Accept commands only from their paired control service, not from arbitrary MQTT publishers.
- Per-device MQTT topic ACLs enforced at broker level (Mosquitto ACL config).
- No anonymous publish on any command topic.
- Command payloads must include `job_id` and `request_id` for traceability.

## Override rules

Manual overrides (physical hardware switches, emergency stops) are always valid regardless of software state. The system does not prevent physical intervention. It logs the discrepancy if telemetry shows unexpected state.

Software-level overrides (emergency mode actions):
- Must be logged immediately.
- Must carry operator identity.
- Must go through the same post-actuation requirements.
