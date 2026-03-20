# ADR-024: Traceability Plane — OTEL + CRK trace_id Threading

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Distributed debugging requires end-to-end trace correlation. Without a threaded trace_id, incident reconstruction across 10 CRK steps and multiple services is impractical.

## Decision
`trace_id` from `InputEnvelope` is threaded through `ExecutionContext` and appears in `ResponseEnvelope` and all `StepAuditRecord`s. OTEL Collector (`infra/otel/otel-collector.yml`) routes traces to Tempo, metrics to Prometheus (with spanmetrics), logs to Loki. `trace-gateway` is config-only (no additional service) unless OTEL SDK + Collector proves insufficient.

Span naming: `crk.{step_name}` (e.g., `crk.6_authz_check`).

## Consequences
- One trace = voice input to response (end-to-end)
- SpanMetrics connector auto-generates per-step latency metrics
- ServiceGraph connector produces runtime dependency map
- `trace_id` mismatch is a P0 bug (caught by operational rubric Invariant 1)
