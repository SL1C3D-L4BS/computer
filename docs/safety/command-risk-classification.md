# Command Risk Classification

Defines the risk class for every job type and the approval requirements for each class.

## Risk class definitions

| risk_class | Description | Approval mode | Audit level |
|-----------|-------------|--------------|------------|
| `INFORMATIONAL` | Read-only query; no physical effect | `NONE` | Optional |
| `LOW` | Reversible adjustment; low consequence if wrong | `AUTO` (policy-gated) | Required |
| `MEDIUM` | Moderate consequence if wrong; recoverable | `AUTO_WITH_AUDIT` | Required |
| `HIGH` | Significant consequence; requires human judgment | `OPERATOR_REQUIRED` | Required + command_log |
| `CRITICAL` | Dangerous or irreversible; wrong action causes physical or safety harm | `OPERATOR_CONFIRM_TWICE` | Required + command_log + incident |

## Job type classification table

### Irrigation and water systems

| Job type | risk_class | Rationale |
|---------|-----------|-----------|
| IrrigationStatusQuery | INFORMATIONAL | Read-only |
| IrrigationRun | MEDIUM | Recoverable; can turn off; some water waste risk |
| IrrigationStop | LOW | Stopping is safe |
| ValveOpen | HIGH | Water damage if wrong zone; requires operator |
| ValveClose | LOW | Closing is generally safe |
| LeakIsolation | HIGH | Emergency shutoff; orchestrator verifies correct valve |
| PumpOverride | HIGH | Pump damage risk; operator required |

### Greenhouse climate

| Job type | risk_class | Rationale |
|---------|-----------|-----------|
| GreenhouseStatusQuery | INFORMATIONAL | Read-only |
| VentCycle | LOW | Reversible; low consequence |
| VentOpen | LOW | Reversible |
| VentClose | MEDIUM | Risk of high temperature/humidity if stuck closed |
| HeaterSetpoint | MEDIUM | Frost risk if set too low; recoverable |
| HeaterOverride | HIGH | Frost damage or fire risk; operator required |
| CO2Injection | HIGH | Gas handling; operator required |
| FanControl | LOW | Reversible |
| ShadingControl | LOW | Reversible |

### Hydroponics

| Job type | risk_class | Rationale |
|---------|-----------|-----------|
| NutrientDose | MEDIUM | Nutrient lockout risk; recoverable with flush |
| pHAdjust | MEDIUM | pH extremes damage plants; recoverable |
| ECCheck | INFORMATIONAL | Read-only |
| FlumeFlush | LOW | Flush is safe |
| PumpCalibration | HIGH | Calibration affects dose accuracy; operator verification |
| ChemicalDoseOverride | CRITICAL | Wrong dose can kill crop or create safety hazard |

### Energy management

| Job type | risk_class | Rationale |
|---------|-----------|-----------|
| EnergyStatusQuery | INFORMATIONAL | Read-only |
| TariffModeSwitch | LOW | Reversible; affects billing only |
| GridChargeEnable | MEDIUM | Battery management; recoverable |
| GridChargeDisable | LOW | Reversible |
| PeakShaving | LOW | Automatic load reduction; reversible |
| BatteryDischarge | MEDIUM | Battery health concern if below threshold |
| GridDisconnect | CRITICAL | Loss of power; requires operator |
| LoadShedding | HIGH | Service interruption; requires operator |

### Security

| Job type | risk_class | Rationale |
|---------|-----------|-----------|
| SecurityStatusQuery | INFORMATIONAL | Read-only |
| CameraStreamQuery | INFORMATIONAL | Read-only |
| IncidentAcknowledge | LOW | Operator action; no physical effect |
| AlarmAcknowledge | LOW | No physical effect |
| LockOverride | CRITICAL | Physical security; irreversible without key |
| AlarmActivate | HIGH | Causes response; operator verification |

### Robotics

| Job type | risk_class | Rationale |
|---------|-----------|-----------|
| RoverStatusQuery | INFORMATIONAL | Read-only |
| RoverWaypointMission | HIGH | Physical autonomy; collision and damage risk |
| RoverSoilSample | HIGH | Physical action; requires planning validation |
| RoverReturnToDock | MEDIUM | Recovery action; generally safe |
| RoverSafeStop | LOW | Stopping is safe |
| DroneStatusQuery | INFORMATIONAL | Read-only |
| DroneMission | CRITICAL | Airspace; FAA; collision risk; requires operator + checklist |
| DroneLandNow | HIGH | Emergency landing; risk if wrong location |
| DroneArm | CRITICAL | Physical hazard; never autonomous |

## Approval flow per class

| risk_class | Approval flow |
|-----------|--------------|
| INFORMATIONAL | No approval; executes immediately |
| LOW | Auto-approved by policy if preconditions met; logged |
| MEDIUM | Auto-approved by policy if preconditions met; logged with audit event |
| HIGH | Queued in ops-web approval queue; FOUNDER_ADMIN or MAINTENANCE_OPERATOR must approve; timeout after 30 min → FAILED |
| CRITICAL | Queued; FOUNDER_ADMIN must approve; second confirmation required ("I confirm"); timeout after 10 min → FAILED |

## AI-originated job handling

Jobs with `origin: ai_advisory`:
- MAX risk_class for auto-approval: LOW
- Any AI-originated job with risk_class >= MEDIUM requires operator review regardless of policy
- This is enforced in orchestrator's policy engine, not just in prompt

This prevents an AI advisory loop from issuing a series of LOW-risk jobs that aggregate into a HIGH-risk outcome (mitigation: job rate limiting per asset per time window).
