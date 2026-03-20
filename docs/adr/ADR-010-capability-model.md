# ADR-010: Normalized asset and capability model

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Physical hardware changes: pumps fail and get replaced, cameras get upgraded, sensors get swapped. If the orchestrator references vendor-specific entity names (`switch.irrigation_valve_123`), every hardware change requires code changes in the orchestrator. This is fragile and untestable.

## Decision

Introduce a **normalized asset and capability model**:

1. Every physical device has a stable **asset_id** (UUID) in the digital-twin registry.
2. Every asset has **capability tags** that describe what it can do, not who made it.
3. The orchestrator requests actions by capability and zone, not by vendor entity name.
4. Adapters translate between vendor entity names and canonical asset IDs.

### Capability tag taxonomy

```
sensor:{type}          # sensor:temperature, sensor:ph, sensor:flow, sensor:motion
actuator:{type}        # actuator:valve, actuator:relay, actuator:pump
robot:{type}           # robot:rover, robot:drone
compute:{type}         # compute:edge, compute:gateway
camera:{type}          # camera:fixed, camera:ptz
power:{type}           # power:battery, power:grid, power:solar
```

### Job targeting by capability

```python
# CORRECT: orchestrator targets by capability + zone
job = Job(
    type="IrrigationRun",
    target_capability="actuator:valve:irrigation",
    target_zone="north",
    parameters={"duration_seconds": 1800}
)

# The adapter resolves this to: switch.irrigation_valve_north_zone_001
# Core never sees the vendor name.
```

### Digital-twin asset registry

```json
{
  "asset_id": "asset_valve_irrigation_north_001",
  "name": "North Irrigation Valve",
  "type": "actuator:valve:irrigation",
  "zone": "north",
  "location": "field_north",
  "vendor_entity": "switch.irrigation_valve_north_001",  // adapter-only
  "capabilities": ["open", "close", "status"],
  "state": {"position": "closed", "last_updated": "2026-03-19T10:00:00Z"},
  "qualification_level": "QA4"
}
```

The `vendor_entity` field is only used by the ha-adapter. Orchestrator never reads it.

## Consequences

- Replacing a pump or sensor requires updating only the digital-twin asset record and the adapter's entity map — not the orchestrator or job schemas.
- The orchestrator is testable without real hardware by substituting mock assets.
- New device types are added to the digital-twin without touching core logic.
- This boundary is enforced by the CI contract-gate (no vendor entity patterns in core).
