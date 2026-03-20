# ADR-005: Rover precedes drone

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

Computer includes both a ground rover (ROS2/Nav2) and a drone (PX4). Both require significant development effort. The question is build order.

## Decision

Build and deploy the rover before the drone.

## Reasons

1. **Safety burden**: Drones operate in airspace with FAA regulatory requirements (Part 107 or recreational rules). Rovers operate on private land with no airspace concerns.

2. **Recovery**: A rover that fails stops in place. A drone that fails falls. Recovery from rover failure is walking to it. Recovery from drone failure may involve property damage or injury.

3. **Testing cycles**: Rover testing can happen daily, indoors (in a large space), or in a constrained yard. Drone testing requires favorable weather, open airspace, and a clear area.

4. **ROS2 and Nav2 prove the robotics infrastructure**: The ROS2 bridge, orchestrator integration, HIL CI lane, and audit trail are all built and proven with the rover before adding the additional complexity of PX4 and uXRCE-DDS.

5. **uXRCE-DDS compatibility risk**: The known v2 client vs v3 agent incompatibility in PX4/ROS2 bridging is a risk that is isolated to the drone. Rover uses standard ROS2 Nav2 without this complication.

## Consequences

- Phase F (rover) precedes Phase G (drone) in the build order.
- All robotics CI infrastructure (SITL gate, HIL gate, self-hosted runner) is proven with the rover before drone development begins.
- Drone development begins only after rover achieves `robotics-stable` release class.
- This does not preclude PX4 SITL development in parallel during Phase F; it only means field deployment follows the order.
