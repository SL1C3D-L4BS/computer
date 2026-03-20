# ADR-003: Home Assistant is an integration and UI plane, not the system of record

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Home Assistant (HA) is excellent for device integration, dashboards, and simple automations. It is not designed to be a safety-critical orchestration engine. Using HA as the source of truth for job state, audit, and policy would couple the system to HA's availability and data model.

## Decision

Home Assistant is an **integration and UI plane only**. It is not the system of record for:
- Job state (owned by orchestrator + Postgres)
- Asset state truth (owned by digital-twin + Postgres)
- Command audit (owned by orchestrator + Postgres)
- Policy evaluation (owned by orchestrator + packages/policy/)

HA is used for:
- Device integration (reading entity states from sensors, relays, etc.)
- Dashboards and Lovelace UI
- Simple automations that do not require safety gates
- Notification routing

## Implementation

- `services/ha-adapter/` receives HA state changes and translates them to canonical events.
- ha-adapter publishes to MQTT event topics; never to command topics.
- ha-adapter updates digital-twin asset state via HTTP API.
- HA is NOT called by orchestrator to execute commands; orchestrator calls control services directly.
- HA automations that involve safety-critical actions (irrigation, heating) are replaced by orchestrator jobs.

## Consequences

- Computer continues to operate when HA is down (except HA dashboards).
- HA upgrade schedule is decoupled from orchestrator upgrade schedule.
- HA is not on the critical path for any physical control action.
- HA dashboards remain valuable for household UX and monitoring.
- Two sources of truth for entity state during sync delays are expected and acceptable; digital-twin is authoritative.
