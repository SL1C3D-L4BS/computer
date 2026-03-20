# End-to-End Tracing Plan

**Status:** Authoritative  
**Owner:** Platform  
**ADR:** ADR-024 (Traceability Plane)  
**Config:** `infra/otel/otel-collector.yml`

---

## Core Principle

**One trace = voice input to response.**

Every CRK execution loop run produces exactly one distributed trace. The `trace_id` from `InputEnvelope` threads through `ExecutionContext` and appears in `ResponseEnvelope` and every step audit record.

---

## trace_id Invariant

```python
# InputEnvelope
envelope = InputEnvelope(raw_input="...", trace_id="crk-abc123", ...)

# ExecutionContext carries it through all 10 steps
ctx = ExecutionContext(trace_id="crk-abc123", ...)

# ResponseEnvelope — MUST match
response = ResponseEnvelope(trace_id="crk-abc123", ...)  # verified by rubric

# Every StepAuditRecord
audit = StepAuditRecord(trace_id="crk-abc123", step="6_authz_check", ...)
```

The operational rubric check "trace_id continuity" verifies this end-to-end.

---

## Span Naming Convention

All CRK spans follow the naming pattern: `crk.{step_name}`

| Step | Span Name |
|------|-----------|
| 1 | `crk.1_input_ingestion` |
| 2 | `crk.2_intent_classification` |
| 3 | `crk.3_context_resolution` |
| 4 | `crk.4_plan_generation` |
| 5 | `crk.5_workflow_binding` |
| 6 | `crk.6_authz_check` |
| 7a | `crk.7a_tool_invocation` |
| 7b | `crk.7b_control_job_bind` |
| 8 | `crk.8_state_update` |
| 9 | `crk.9_attention_decision` |
| 10 | `crk.10_response_render` |

Service-level spans nest inside the CRK step span:
```
crk.6_authz_check
  └── authz-service.evaluate_policy
crk.7a_tool_invocation
  └── mcp-gateway.policy.evaluate
  └── mcp-gateway.tool.execute
```

---

## OTEL Collector Architecture

See `infra/otel/otel-collector.yml` for full configuration.

```
Services (runtime-kernel, attention-engine, etc.)
    │
    ▼ OTLP gRPC (port 4317) / HTTP (port 4318)
OpenTelemetry Collector
    │
    ├── Traces → Tempo (via OTLP exporter)
    ├── Metrics → Prometheus (via RemoteWrite)
    │   └── SpanMetrics connector: auto-generate latency + error metrics from spans
    │   └── ServiceGraph connector: dependency map
    └── Logs → Loki (structured)
```

---

## Connectors

### SpanMetrics

Auto-generates service latency and error rate metrics from spans:

```yaml
connectors:
  spanmetrics:
    histogram:
      explicit:
        buckets: [5ms, 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s]
    dimensions:
      - name: crk.step    # Per-step latency breakdown
      - name: service.name
```

This means every CRK step gets automatic P50/P95/P99 latency metrics without manual instrumentation.

### ServiceGraph

Auto-discovers service dependencies from span parent-child relationships. Used for the runtime dependency map in Grafana.

---

## Key Attributes

All spans should include:

| Attribute | Value |
|-----------|-------|
| `trace_id` | InputEnvelope.trace_id (carried through ExecutionContext) |
| `crk.step` | Step name (e.g., `6_authz_check`) |
| `crk.status` | Step status: `ok`, `noop`, `stub`, `error` |
| `user_id` | ExecutionContext.user_id |
| `mode` | ExecutionContext.mode |
| `risk_class` | ExecutionContext.risk_class |
| `service.name` | Service name (e.g., `runtime-kernel`) |
| `service.namespace` | `computer` |

---

## Alerting Rules

| Alert | Condition | Severity |
|-------|-----------|---------|
| CRK step latency > 2s | `crk_step_duration_p99 > 2000ms` | WARNING |
| Authz deny rate > 5% | `crk_6_authz_check_deny_rate > 0.05` | WARNING |
| Step 7b failure rate > 1% | `crk_7b_error_rate > 0.01` | CRITICAL |
| trace_id mismatch detected | `rubric_check{name="trace_id_continuity"} == 0` | CRITICAL |
| Emergency interrupt | `crk.intent_class == "emergency.interrupt"` | PAGE |

---

## Sampling Strategy

```yaml
processors:
  probabilistic_sampler:
    sampling_percentage: 10  # 10% of LOW-risk traces

# Always sample:
# - CRITICAL risk_class
# - ERROR status
# - emergency.* intent_class
# - Any trace where authz denied
```

100% of CRITICAL and ERROR traces are always retained.

---

## Local Development

In local development mode, use the debug exporter:

```yaml
exporters:
  debug:
    verbosity: basic      # Print span summaries to stdout
    sampling_initial: 5   # Print first 5 spans per unique operation
    sampling_thereafter: 200
```

`task otel:debug` starts the collector with debug output for local trace inspection.

---

## Grafana Dashboards

| Dashboard | Source |
|-----------|--------|
| CRK Step Latency | SpanMetrics → Prometheus |
| Service Dependency Map | ServiceGraph → Prometheus |
| Error Rate by Step | SpanMetrics |
| Trace Explorer | Tempo (via Grafana Tempo datasource) |
| Log Aggregation | Loki (crk.step + service.name labels) |
