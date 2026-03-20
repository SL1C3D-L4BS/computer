# E-Stop and Fail-Safe Specification

Defines emergency stop mechanisms and fail-safe behaviors for all physical systems.

## Principle: fail safe, not fail open

When any part of the system fails, the default behavior must be the **safest physical state**, not the most convenient one.

| System | Fail-safe state | Rationale |
|--------|----------------|-----------|
| Irrigation valves | CLOSED | Prevent water damage |
| Greenhouse vents | OPEN (partially) | Prevent overheating |
| Greenhouse heaters | OFF | Prevent fire; frost risk is secondary |
| Hydroponics pumps | OFF | Prevent nutrient overdose |
| Chemical dosing pumps | OFF | Prevent chemical overconcentration |
| Energy grid connection | MAINTAIN (no-change) | Avoid unexpected power loss |
| Rover | STOP IN PLACE | Prevent collision or out-of-bounds |
| Drone | HOVER, then RTH | Prevent crash; return-to-home if GPS available |
| Security cameras | CONTINUE RECORDING | No fail-safe state for passive sensors |
| MQTT broker | SERVICES ENTER DEGRADED MODE | Control services stop accepting commands |

## Hardware E-stop mechanisms

### Level 0 — Physical (always overrides software)

Every actuator that can cause physical harm must have a physical disconnect:
- Irrigation valves: manual ball valves upstream of all automated valves
- Chemical dosing pumps: physical master pump switch on panel
- Heaters: thermal cutoff fuse + manual breaker
- Rover: physical E-stop button on chassis (red mushroom button)
- Drone: RC transmitter kill switch
- Grid power: manual transfer switch

These physical E-stops cannot be disabled by software. They are the ultimate safety layer.

### Level 1 — Control service E-stop

Each control service implements a local E-stop command:
```
MQTT topic: computer/{site}/{domain}/{asset}/e_stop
Payload: {"job_id": "...", "triggered_by": "...", "reason": "..."}
```

On receipt of `e_stop`:
1. Immediately transition controlled asset to fail-safe state.
2. Reject all new commands until reset.
3. Publish E-stop confirmation on ack topic.
4. Log E-stop event to Postgres.

### Level 2 — Orchestrator E-stop

Orchestrator can issue an E-stop for a job or asset:
- `orchestrator.e_stop(asset_id)` — stops all active jobs on asset
- `orchestrator.e_stop_all()` — stops all EXECUTING jobs; used for site-wide emergency

E-stop at orchestrator level:
1. Transitions all affected jobs to ABORTED state.
2. Dispatches E-stop commands to relevant control services via MQTT.
3. Logs all transitions to audit.
4. Sets asset status to `E_STOPPED` in digital-twin.

### Level 3 — Emergency mode E-stop

Emergency mode can trigger orchestrator E-stop plus specific physical recovery actions. See `emergency-mode-spec.md`.

## Rover fail-safe

| Trigger | Rover behavior |
|---------|---------------|
| Loss of MQTT connection | Stop in place; wait 30 seconds; attempt reconnect |
| Mission abort from orchestrator | Stop; return to dock |
| E-stop command | Immediate stop; hold position |
| GPS loss | Stop in place; do not resume waypoint mission |
| Battery below 15% | Return to dock regardless of mission state |
| Physical E-stop button | Immediate motor stop; enter hardware lock state |

Rover must not move after physical E-stop button without a hardware reset sequence.

## Drone fail-safe

| Trigger | Drone behavior |
|---------|---------------|
| Loss of RC link | RTH (return-to-home) at configured altitude |
| Loss of telemetry/MQTT | Continue current mission segment; return home after segment |
| Mission abort from orchestrator | Land at nearest safe point; operator confirmation to move |
| GPS loss | Hover (if GPS was acquired); land if GPS was never acquired |
| Battery below 20% | Return to home immediately; abort mission |
| Emergency DroneLandNow command | Land at current position (operator accepts risks) |
| Physical kill switch | Motor cutoff; this is a last resort due to crash risk |

## Software watchdog

Each control service runs a watchdog timer:
- Expected heartbeat from orchestrator every 30 seconds
- If no heartbeat for 90 seconds: enter degraded mode (no new commands; maintain current state)
- If no heartbeat for 5 minutes: transition to fail-safe state

Orchestrator runs a watchdog on MQTT broker connectivity:
- If MQTT is disconnected for 30 seconds: log alert; services auto-enter degraded mode
- If MQTT is disconnected for 5 minutes: trigger ops-web alert

## Reset procedure after E-stop

A control service that has been E-stopped requires an explicit reset before accepting commands:

1. Operator reviews E-stop reason in ops-web incident queue.
2. Operator physically verifies system state (visual inspection for critical systems).
3. Operator issues reset via ops-web: `POST /jobs {type: "AssetReset", asset_id: "..."}`
4. Orchestrator verifies no conflicting active jobs.
5. Control service transitions from `E_STOPPED` to `READY`.
6. Reset event logged to Postgres.

Automated reset is not permitted for HIGH or CRITICAL risk assets (rover, drone, heaters, chemical dosing).
