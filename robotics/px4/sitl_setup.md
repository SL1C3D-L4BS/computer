# PX4 SITL Setup — Drone Phase G

## Prerequisites

```bash
# Install PX4 Autopilot (v1.15+)
git clone --recursive https://github.com/PX4/PX4-Autopilot.git
cd PX4-Autopilot
bash ./Tools/setup/ubuntu.sh
```

## Running SITL

```bash
# Start PX4 SITL with Gazebo (iris model)
cd PX4-Autopilot
make px4_sitl_default gazebo-classic VEHICLE_MODEL=iris

# In another terminal, start drone-control service
cd /path/to/computer
docker compose -f infra/docker/compose.services.yml up drone-control
```

## MAVLink Connection

The drone-control service connects to PX4 SITL at:
- Host: `127.0.0.1` (or `PX4_SITL_HOST` env var)
- Port: `14540` (default MAVLink UDP, or `PX4_SITL_PORT` env var)

## SITL Scenarios

```bash
# Run supervised mission SITL test
python3 robotics/simulation/drone_sitl.py --scenario supervised_waypoint

# Run emergency RTL SITL test
python3 robotics/simulation/drone_sitl.py --scenario emergency_rtl

# Run battery low test
python3 robotics/simulation/drone_sitl.py --scenario battery_low_rtl
```

## CI Gate (F07)

The robotics CI workflow (`robotics.yml`) runs drone SITL tests on
self-hosted runners when the PR has the `needs-sitl` label.

All drone operations require `OPERATOR_CONFIRM_TWICE` approval (CRITICAL risk).
AI advisory layer cannot arm or fly the drone (ADR-002).

## Hardware Qualification

Drone requires `QA2` qualification level before field missions.
See `docs/safety/hardware-qualification.md` for drone checklist.
