# ADR-008: OSINT providers are optional adapters, not core dependencies

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

OSINT (Open Source Intelligence) feeds — fire dispatch (PulsePoint), weather alerts, CAD feeds, Broadcastify scanner audio — add situational awareness but have licensing restrictions, API rate limits, and are not universally available.

## Decision

OSINT providers are **optional adapters** that implement the OSINT adapter contract. They are not core dependencies. The system must operate fully without any OSINT provider enabled.

## Implementation

- `services/osint-ingest/` contains the OSINT ingest service and provider plugin interface.
- Each provider is a plugin (PulsePoint, weather API, fire perimeter feed, etc.).
- `features.osint_enabled: false` in site.yaml disables the entire module.
- When disabled, the incident queue continues to work with Frigate events and sensor alerts.

## Licensing and API constraints

- PulsePoint: requires license agreement; check current terms before enabling.
- Broadcastify: audio streams; transcription adds compute cost; optional.
- Weather APIs: rate limits; fall back to local sensor data if API unavailable.

## Consequences

- Computer core works without OSINT.
- OSINT adds situational awareness (fire risk, public safety events) but is supplementary.
- New OSINT providers can be added without touching core services.
- If an OSINT provider changes its API or licensing, only the provider plugin needs updating.
