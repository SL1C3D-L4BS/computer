# ADR-025: CRK is the Primary Request Execution Loop (No Second Lifecycle)

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Multiple services (assistant-api, control-api, voice-gateway) each had partial execution logic, creating hidden parallel lifecycles that diverged over time: different auth, tracing, and memory behaviors per surface.

## Decision
ALL requests from ALL surfaces route through `runtime-kernel POST /execute`. Surfaces are dumb: they create `InputEnvelope` and call `/execute`. There is no "simple chat stays in assistant-api" path. `runtime-kernel` decides which steps no-op for a given request — not the surface.

## Consequences
- One execution path = consistent auth, tracing, memory behavior for all requests
- assistant-api: InputEnvelope creator + session holder only
- control-api: request surface + auth only; emits InputEnvelope
- Two lifecycles = future drift = bugs
