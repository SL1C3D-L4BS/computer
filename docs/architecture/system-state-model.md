# System State Model

**Status:** SPECIFIED  
**Authority:** runtime-kernel  
**Contract ref:** packages/runtime-contracts/models.py  
**ADR refs:** ADR-017 (workflow plane), ADR-022 (local-first sync), ADR-027 (mode transitions)

---

## Governing principle

Computer is a **partially observable** system. No single component has full knowledge of the global state. The state model defines what is known, by whom, with what confidence, and for how long. Every component that reads or writes state must declare its authority partition.

---

## Global State Decomposition

### 1. Operational State

**Owner:** `orchestrator` (canonical), `runtime-kernel` (read-only snapshot)  
**Update source:** orchestrator job state machine, workflow-runtime signals  
**Persistence:** PostgreSQL (`orchestrator` schema)  
**Decay semantics:** none — jobs are terminal (COMPLETED | FAILED | CANCELLED)  
**Confidence semantics:** binary — a job either exists with a known state or it does not

| Variable | Type | Description |
|----------|------|-------------|
| `active_jobs` | `list[JobRecord]` | In-flight site control jobs |
| `workflow_ids` | `list[str]` | Temporal workflow IDs in RUNNING state |
| `asset_health` | `dict[str, AssetStatus]` | Per-asset health flags |
| `active_incidents` | `list[IncidentRecord]` | Open safety incidents |
| `system_health_flags` | `list[str]` | Degraded subsystem names (e.g. `MQTT_DOWN`) |

---

### 2. Assistant State

**Owner:** `runtime-kernel`  
**Update source:** CRK execution loop steps 2, 3, 8  
**Persistence:** In-memory with write-through to Redis (mode_by_surface); ephemeral for dialog  
**Decay semantics:** mode decays to FAMILY on shared-device ambiguity (see ADR-027); dialog context expires after session timeout  
**Confidence semantics:** `ModeConfidence` attached to each mode entry (see uncertainty model)

| Variable | Type | Description |
|----------|------|-------------|
| `mode_by_surface` | `dict[str, Mode]` | Per `{user_id}:{surface}` sticky mode |
| `mode_confidence_by_surface` | `dict[str, float]` | `IdentityConfidence` for each mode entry; [0,1] |
| `active_dialog` | `DialogSession \| None` | Current multi-turn session, if any |
| `trust_tier_by_user` | `dict[str, str]` | T0–T4 trust tier per user |
| `pending_clarifications` | `list[ClarificationRequest]` | Awaiting user elicitation responses |

---

### 3. Human State Estimates

**Owner:** `attention-engine` (primary), `context-router` (mode inference)  
**Update source:** observation records from user interactions (ack, dismissal, silence, corrections)  
**Persistence:** sliding window in-memory; checkpointed every 60s to Redis  
**Decay semantics:** `attention_load` decays toward 0.0 at rate 0.02/min after last interaction; estimates expire after 10 min without signal  
**Confidence semantics:** all estimates are probabilistic; `IdentityConfidence` attached to per-user estimates on shared devices

| Variable | Type | Description |
|----------|------|-------------|
| `attention_load` | `float [0,1]` | Current cognitive load estimate for primary user |
| `likely_available_at` | `str \| None` | ISO 8601 estimate of next availability window |
| `identity_confidence` | `float [0,1]` | Certainty that the current speaker is the identified user |
| `role_in_context` | `str` | Inferred role: `founder` \| `parent` \| `guest` \| `child` \| `operator` |
| `estimated_location` | `str \| None` | Physical zone (e.g. `office`, `kitchen`), if known |

---

### 4. Memory State

**Owner:** `memory-service`  
**Update source:** user corrections, workflow completions, assistant interactions, scheduled archival jobs  
**Persistence:** PostgreSQL (vector + metadata); archival to object storage  
**Decay semantics:** per memory class (see `docs/product/memory-lifecycle-policy.md`); freshness [0,1] decays continuously  
**Confidence semantics:** each memory entry carries `retrieval_confidence` (relevance score at retrieval time) and `source_confidence` (how certain we are of the fact's accuracy)

| Variable | Type | Description |
|----------|------|-------------|
| `personal_memories` | `list[MemoryEntry]` | User-scoped facts, preferences, history |
| `household_memories` | `list[MemoryEntry]` | Shared family facts and notes |
| `work_memories` | `list[MemoryEntry]` | Work context, decisions, commitments |
| `site_memories` | `list[MemoryEntry]` | Site incidents, equipment history, calibration records |
| `inferred_habits` | `list[HabitRecord]` | System-inferred behavioral patterns with confidence |

**Memory entry schema (base):**

| Field | Type | Semantics |
|-------|------|-----------|
| `id` | `str` | Stable UUID |
| `scope` | `MemoryScope` | Access control boundary |
| `content` | `str` | Fact or note |
| `source` | `str` | `explicit` \| `inferred` \| `observed` |
| `freshness` | `float [0,1]` | 1.0 when written; decays per class hazard function |
| `confidence` | `float [0,1]` | Source confidence at write time |
| `created_at` | `str` | ISO 8601 |
| `last_accessed_at` | `str` | Updated on every retrieval |
| `status` | `str` | `ACTIVE` \| `ARCHIVED` \| `SUPERSEDED` \| `DELETED` |
| `superseded_by` | `str \| None` | Reference to correction record if SUPERSEDED |

---

### 5. Environment State

**Owner:** `digital-twin` service  
**Update source:** MQTT sensor events, Home Assistant webhooks, Frigate detections  
**Persistence:** time-series (InfluxDB or equivalent); current values in Redis  
**Decay semantics:** readings expire after their `max_age_s` (configurable per sensor type); stale readings flag `SENSOR_STALE` in `system_health_flags`  
**Confidence semantics:** `EventSeverityConfidence` attached to sensor readings; cross-validated with redundant sensors where available

| Variable | Type | Description |
|----------|------|-------------|
| `greenhouse_readings` | `dict[str, SensorReading]` | Temperature, humidity, CO2, soil moisture |
| `security_events` | `list[SecurityEvent]` | Frigate detections, door/motion events |
| `energy_readings` | `dict[str, float]` | Per-circuit power consumption |
| `weather_current` | `WeatherSnapshot \| None` | Local weather aggregate |
| `zone_occupancy` | `dict[str, bool]` | Per-zone occupancy estimate |

---

### 6. Meta State

**Owner:** `runtime-kernel`  
**Update source:** self-monitoring, service health checks, confidence engine, model health probes  
**Persistence:** in-memory; emitted as OTEL metrics  
**Decay semantics:** health flags are set on detection and cleared on recovery confirmation  
**Confidence semantics:** `model_health` is a scalar estimate of LLM response quality based on recent eval scores

| Variable | Type | Description |
|----------|------|-------------|
| `uncertainty_estimates` | `dict[str, float]` | Per-partition aggregate uncertainty [0,1] |
| `degradation_mode` | `str \| None` | `DEGRADED_MQTT` \| `DEGRADED_LLM` \| `DEGRADED_AUTHZ` etc. |
| `last_successful_sync_at` | `str` | ISO 8601; timestamp of last full state sync |
| `model_health` | `float [0,1]` | LLM quality estimate from eval-runner scores |
| `runtime_version` | `str` | Deployed version of runtime-kernel |
| `active_policy_version` | `str` | Version string of the active authz policy |

---

## State Update Authority Table

No service may update another service's canonical state partition.

| Component | May Write | May Read |
|-----------|-----------|----------|
| `runtime-kernel` | Assistant state, Meta state | All (via service APIs) |
| `orchestrator` | Operational state | Operational, Meta |
| `workflow-runtime` | Own workflow state | Operational, Assistant (read-only) |
| `attention-engine` | Human estimate state | Assistant, Human estimate |
| `memory-service` | Memory state | Memory |
| `digital-twin` | Environment state | Environment |
| `authz-service` | None (stateless policy) | Assistant (mode), Operational |
| `mcp-gateway` | None (stateless router) | Assistant (mode, trust tier) |

---

## Composite State Object (ComputerState)

`ComputerState` (in `packages/runtime-contracts/models.py`) is the **read-only snapshot** used by:
- `GET /state` endpoint of runtime-kernel
- family-web dashboard
- founder mode briefing

It is a projection, not the canonical store. It must never be written to directly.

---

## Observability Requirements

- All state transitions emit OTEL spans with `state.partition` attribute
- State-write operations include the writing service name in span metadata
- Stale readings (confidence below threshold) emit `state.staleness.warning` metric
- Mode changes emit `state.mode_transition` event with `reason` field (invariant I-07)
