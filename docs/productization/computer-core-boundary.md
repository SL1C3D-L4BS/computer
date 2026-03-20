# Computer Core Boundary

Defines what is in `computer-core` and what is site-specific or adapter-specific. This boundary enables Computer to be reusable or adaptable without code surgery.

## Core boundary definition

`computer-core` contains everything that is **not specific to a particular physical site, household, or hardware vendor**. It is the portable, reusable foundation.

### What is in computer-core

| Component | Package/Path | Reason |
|-----------|-------------|--------|
| Orchestrator kernel | `apps/orchestrator/` | Job model, state machine, policy engine, audit — generic |
| Digital-twin service | `apps/digital-twin/` | Asset registry concept — not Spokane-specific |
| Control-api | `apps/control-api/` | Auth and routing layer — generic |
| Event-ingest | `apps/event-ingest/` | Event normalization pipeline — generic |
| Assistant-api | `apps/assistant-api/` | Session and conversation management — generic |
| Model-router | `apps/model-router/` | Model selection and guardrails — generic |
| Context-router | `services/context-router/` | Intent and context classification — generic |
| Memory-service | `services/memory-service/` | Memory store and scoped retrieval — generic |
| Identity-service | `services/identity-service/` | Household identity and roles — generic |
| Contracts package | `packages/contracts/` | Job, asset, event, command schemas — generic |
| Assistant contracts | `packages/assistant-contracts/` | Conversation and memory schemas — generic |
| Policy packages | `packages/policy/` | Command, assistant, capability policy — generic logic (not rules) |
| Persona package | `packages/persona/` | Persona spec and style rules — generic behavioral contract |
| SDK package | `packages/sdk/` | Internal client SDKs — generic |
| UI package | `packages/ui/` | Shared UI components — generic |
| Prompts package | `packages/prompts/` | Prompt templates — generic |

### What is NOT in computer-core

| Component | Where it lives | Reason |
|-----------|---------------|--------|
| Spokane zone definitions | `packages/config/site.yaml` | Site-specific |
| Avista tariff data | `packages/config/tariffs/avista.yaml` | Site-specific |
| WSU frost calendar | `packages/config/crops/spokane-frost.yaml` | Site-specific |
| Greenhouse zone layouts | `packages/config/zones/` | Site-specific |
| Asset IDs and topology | `data/seed/` | Site-specific |
| MQTT topic site prefix | `packages/config/site.yaml` | Site-specific (`computer/spokane/...`) |
| HA adapter | `services/ha-adapter/` | Vendor-specific |
| Frigate adapter | `services/frigate-adapter/` | Vendor-specific |
| Device adapters | `services/*-adapter/` | Vendor-specific |
| Control services | `services/greenhouse-control/` etc. | Site behavior (uses core orchestrator) |
| OSINT provider | `services/osint-ingest/` | Optional module |

## Core / non-core interface

Core services communicate through contracts only. They never import site-specific config directly.

```python
# CORRECT: orchestrator requests by capability
job = Job(
    type="IrrigationRun",
    target_capability="actuator:valve:irrigation",
    target_zone="north",
    # No: "switch.irrigation_valve_north_123"
)

# INCORRECT: vendor entity name in core
job = Job(
    type="IrrigationRun",
    target_entity="switch.irrigation_valve_north_123"  # ← FORBIDDEN in core
)
```

Site-specific mapping from zone + capability → vendor entity is the job of adapters and the digital-twin asset registry.

## Testing the boundary

The contract-gate CI job includes a boundary check:
- Scan `apps/orchestrator/`, `apps/digital-twin/`, `packages/contracts/` for HA entity patterns (`switch.`, `light.`, `sensor.`, `input_boolean.`).
- Any match fails the build.

This enforces the boundary mechanically.
