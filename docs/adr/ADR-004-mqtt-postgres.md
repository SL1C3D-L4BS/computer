# ADR-004: MQTT is edge transport; PostgreSQL is control truth

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

The system needs a messaging layer for real-time telemetry and commands from edge devices, and a durable store for job state, audit, and asset history. Using MQTT alone for everything (including job state) would mean losing state on broker restart. Using a database for everything (including real-time telemetry) would create polling-based latency.

## Decision

Two planes:

1. **MQTT (Eclipse Mosquitto)** — Real-time edge transport only:
   - Topic families: `telemetry`, `event`, `command_request`, `command_ack`, `health`
   - Used for: device telemetry, sensor events, command dispatch, acknowledgments, health heartbeats
   - NOT used for: durable state, job lifecycle, audit, configuration
   - Retained topics: only for last-known state (LWT, config payloads)

2. **PostgreSQL** — Durable control plane:
   - Stores: jobs, asset definitions, command_log, audit events, event history, site config snapshots
   - Never used for: real-time telemetry (too slow; use MQTT + time-series if needed)

## Topic naming convention

```
computer/{site}/{domain}/{asset_id}/{channel}
```

Examples:
- `computer/spokane/greenhouse/zone-a/telemetry`
- `computer/spokane/rover/rover-01/command_request`
- `computer/spokane/control/irrigation-north/command_ack`

Command topics are never consumed directly by hardware. Receiving services validate and then actuate.

## Consequences

- State survives MQTT broker restart (jobs are in Postgres).
- Real-time commands have low latency (MQTT).
- event-ingest subscribes to MQTT and writes canonical events to Postgres asynchronously.
- Redis is used for ephemeral caching and short-lived workflow state (not truth).
- NATS is not used in v1. MQTT + Postgres is sufficient; NATS adds complexity without a proven need.
