# Degraded Mode Specification

Defines how the Computer system behaves when infrastructure or services are unavailable. The system must degrade gracefully, not silently.

## Degraded mode principles

1. **No new risk**: When degraded, do not start new physical control actions.
2. **Maintain safe state**: Continue existing safe-state conditions; do not change state unpredictably.
3. **Surface the failure**: Operator must be able to see which component is degraded.
4. **Preserve audit**: Even in degraded mode, log what can be logged.
5. **Recover automatically**: When the dependency recovers, services resume normal operation without manual intervention (except for control services; those require explicit operator acknowledgment).

## Infrastructure degradations

### MQTT broker down

| Service | Behavior |
|---------|---------|
| orchestrator | Queues commands; retries on reconnect; no new EXECUTING jobs while MQTT is down |
| greenhouse-control | Holds current actuator state; refuses new commands |
| hydro-control | Holds current state; no new doses |
| event-ingest | Buffers events locally (in-memory queue, max 1000 events); writes on reconnect |
| rover-control | Continues current mission segment; stops at end of segment; awaits reconnect |
| drone-control | Continues current mission segment (PX4 onboard); RTH if link down for > 60 seconds |
| ha-adapter | Pauses entity sync; queues HA events |
| control-api | Returns 503 for any control requests; reads from Postgres cache for status queries |

**Recovery**: On MQTT reconnect, all services re-subscribe and resume. Orchestrator re-dispatches any EXECUTING jobs that have not received ack. Operator is notified of any jobs that were affected.

### PostgreSQL down

| Service | Behavior |
|---------|---------|
| orchestrator | Rejects all new jobs; returns 503 for job submission; continues serving in-memory state for EXECUTING jobs |
| event-ingest | Buffers events in Redis (fallback store); writes to Postgres on recovery |
| digital-twin | Serves from Redis cache; read-only; refuses writes |
| control-api | Read requests served from cache; write/submit returns 503 |
| assistant-api | Cannot write memories or sessions; read-only from Redis cache |
| memory-service | Read from Redis cache; no writes |

**Recovery**: On Postgres reconnect, orchestrator replays buffered jobs, event-ingest drains Redis buffer to Postgres. Operator is notified of any data buffered during outage.

### Redis down

| Service | Behavior |
|---------|---------|
| orchestrator | Uses local in-memory cache; state transitions still work but are not cached |
| assistant-api | Session state temporarily unavailable; sessions must re-authenticate |
| memory-service | Uses Postgres directly (slower; acceptable for short outages) |
| digital-twin | Uses Postgres directly |

**Recovery**: On Redis reconnect, services repopulate cache from Postgres. Sessions may require re-login (acceptable).

## Service degradations

### Orchestrator down

| Service | Behavior |
|---------|---------|
| control-api | Returns 503 for all control requests; status queries from Postgres cache |
| greenhouse-control | Holds current state; local watchdog triggers fail-safe after 5 minutes |
| hydro-control | Holds current state; local watchdog triggers fail-safe after 5 minutes |
| rover-control | Stops at next safe waypoint; awaits orchestrator recovery |
| assistant-api | No site control available; T4 tools return "unavailable"; T0–T3 continue |

**Recovery**: On orchestrator recovery, it replays any EXECUTING jobs from Postgres state and dispatches accordingly. Operator reviews any jobs that were in EXECUTING state during outage.

### AI / model-router down

| Service | Behavior |
|---------|---------|
| assistant-api | Returns T0/T3 responses from rule-based fallbacks; no LLM inference |
| ops copilot | Unavailable; operator sees "AI advisor offline" |
| Site operations | Continue normally; AI is advisory only and never on the critical path |

**Recovery**: model-router reconnects to Ollama/vLLM; assistant resumes full capability.

### Home Assistant down

| Service | Behavior |
|---------|---------|
| ha-adapter | Stops sending HA events; queues reconnect attempts |
| ops-web | HA dashboard panels show "unavailable"; site continues operating |
| greenhouse-control | If using HA entities for sensor data: falls back to direct MQTT sensor readings |

**Recovery**: ha-adapter reconnects; resumes entity sync.

### Frigate down

| Service | Behavior |
|---------|---------|
| frigate-adapter | Stops receiving events; logs "Frigate unavailable" |
| ops-web | Incident queue shows "camera system unavailable" |
| Security | No new AI detections; camera streams may still be accessible directly |

**Recovery**: frigate-adapter reconnects; resumes event processing.

## Network partition (edge autonomy mode)

If the site network is partitioned (e.g., WAN down but local LAN up):
- All local services continue operating normally.
- External OSINT feeds are unavailable; osint-ingest switches to local-only mode.
- Push notifications to external services are queued.
- Computer operates fully locally; local-first design is realized.

If the LAN itself is partitioned (e.g., VLAN segmentation failure):
- L1 control services fall back to direct device communication where possible.
- Orchestrator enters degraded mode for affected VLANs.
- Operator is alerted via any available network path.

## Degraded mode display (ops-web)

The ops-web system status panel shows the health of each tier:

| Tier | Services | Status indicators |
|------|---------|------------------|
| Infrastructure | Postgres, Redis, MQTT | Green / Yellow / Red |
| Kernel | orchestrator, digital-twin | Green / Yellow / Red |
| Control | greenhouse-control, hydro-control, etc. | Green / Yellow / Red per service |
| Assistant | assistant-api, model-router | Green / Yellow / Red |
| Adapters | ha-adapter, frigate-adapter | Green / Yellow / Red |

A yellow status means "degraded but safe." A red status means "down; some capabilities unavailable."

The glue layer (`./bootstrap.sh` health check or a simple supervisor) polls each service's `/health` endpoint every 30 seconds and writes status to a shared Redis key. ops-web reads from this key for the status display.
