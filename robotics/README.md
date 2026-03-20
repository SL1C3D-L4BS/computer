# robotics

> ROS2 workspace, Nav2 navigation, PX4 SITL integration, and simulation environments for ground rover and supervised drone operations.

---

## Overview

The `robotics/` directory contains all ROS2, Nav2, and PX4 components for Computer's physical platform. Rover operations are production-grade with Nav2. Drone operations are supervised-only (ADR-005) with PX4 SITL bridge.

No autonomous flight without explicit operator approval. All robot commands originate from `orchestrator` via MQTT; no AI path writes directly to ROS or PX4.

## Directory Structure

```
robotics/
├── ros2_ws/     — ROS2 workspace (rover navigation, sensor fusion)
├── nav2/        — Nav2 configuration and mission profiles
├── px4/         — PX4 SITL bridge and flight control stubs
├── sim/         — SITL simulation launch configs
└── simulation/  — Social and scenario simulation environments
```

## Safety Constraints

| Constraint | Enforcement |
|-----------|-------------|
| No autonomous flight (ADR-005) | Drone requires operator approval before any mission |
| Safety interlocks (I-04) | Rover halts on active safety interlock |
| AI path isolation | No direct ROS/PX4 calls from assistant-api or model-router |
| Supervised-only drone | PX4 bridge rejects unapproved missions |

## Key Commands

```bash
# Start ROS2 workspace
task sim:ros2-up

# Launch Nav2 with rover
task sim:nav2

# Start PX4 SITL
task sim:px4-sitl

# Run SITL scenarios
task sim:scenarios

# Run social SITL
task sim:socials
```

## Testing

```bash
task ci:milestone-5           # Rover mission integration tests
pytest robotics/tests/ -v     # Unit tests for state machines
```

## Dependencies

| Tool | Version | Purpose |
|------|---------|---------|
| ROS2 Humble | LTS | Robot operating system |
| Nav2 | Current | Ground navigation stack |
| PX4 | 1.14.x | Drone flight control |
| Gazebo | Harmonic | Simulation environment |
| uXRCE-DDS | v2 client | PX4 ROS2 bridge |

> **NOTE:** PX4 uXRCE-DDS uses v2 client; v3 agent is not yet compatible. Do not upgrade the bridge without testing the full SITL pipeline.

## See Also

- [ADR-005: Rover before drone, supervised drone only](../docs/adr/ADR-005-rover-before-drone.md)
- [services/rover-control](../services/rover-control/) — mission executor
- [services/drone-control](../services/drone-control/) — PX4 bridge
