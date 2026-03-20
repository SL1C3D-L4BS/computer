# Hardware-in-Loop (HIL) Gate Plan

Defines the HIL and simulation runbooks required for robotics-stable and field-qualified releases.

## HIL philosophy

HIL gates exist because simulation cannot fully capture real hardware behavior. However, HIL is expensive and slow, so it is:
1. **Required** for field-qualified releases of rover-control and drone-control.
2. **Optional but encouraged** for site-stable releases of greenhouse-control and hydro-control.
3. **Never required** for web/backend services.

Simulation (SITL) gates are cheaper and run more frequently (nightly). SITL must pass before HIL is attempted.

## Gate: Rover SITL (sim-stable prerequisite)

**Environment**: Gazebo Kilted + ROS 2 Nav2 on CI runner  
**Trigger**: Any PR touching `robotics/**` or `services/rover-control/**`

Scenarios that must pass:

1. **Waypoint mission**: Load a 5-waypoint mission; rover completes all waypoints; returns to dock. Assert: all waypoints visited, job transitions to COMPLETED, command_log entry written.

2. **Safe-stop during mission**: Inject safe-stop command at waypoint 3; verify rover stops within 2 seconds; job transitions to ABORTED; audit logged.

3. **Obstacle avoidance**: Place a static obstacle on waypoint 3 path; verify Nav2 replans; rover avoids and continues mission.

4. **Battery low return**: Simulate battery drop to 15%; verify rover abandons mission and returns to dock; job transitions to FAILED with reason "battery_low".

5. **MQTT loss**: Disconnect MQTT mid-mission; verify rover stops at next safe waypoint; reconnects; reports status.

6. **Dock and charge**: Mission completes; rover autonomously docks; charging state reported in digital-twin.

**Pass criteria**: All 6 scenarios complete without manual intervention. All state transitions logged in Postgres.

## Gate: Rover HIL (field-qualified prerequisite)

**Environment**: Real rover on test track; self-hosted runner with ROS 2 and MQTT connectivity  
**Trigger**: Manual trigger only; required before `field-qualified/rover-control` tag

Pre-HIL checklist:
- [ ] Rover passed QA4 hardware qualification
- [ ] SITL gate passed on same code
- [ ] Operator briefed on E-stop procedure
- [ ] Test area clear of obstructions and bystanders
- [ ] RC override radio charged and tested

HIL test sequence:

1. **Boot and health check**: Start rover; verify all ROS2 nodes running; MQTT connected; digital-twin shows rover online.

2. **Teleop test**: Manual teleop 10m forward, 10m back, 360° rotation. Verify odometry matches measured distances within 5%.

3. **Supervised waypoint mission**: 3 waypoints in test area (10m × 10m grid). Operator observes; ready to E-stop. Assert: mission completes; audit logged.

4. **E-stop test**: During teleop, press physical E-stop button. Verify immediate motor stop. Verify no movement until hardware reset.

5. **Orchestrator E-stop**: During mission, issue E-stop via ops-web. Verify rover stops within 3 seconds.

6. **Return-to-dock**: Issue RTH command via ops-web. Verify rover navigates to dock and reports docked.

7. **Operator sign-off form**: Complete and attach to release notes.

**Pass criteria**: All 6 tests pass. Operator signs off. Sign-off recorded in `RELEASES.md`.

## Gate: Drone SITL (sim-stable prerequisite)

**Environment**: PX4 SITL + Gazebo + ROS2 bridge  
**Trigger**: Any PR touching `robotics/px4/**` or `services/drone-control/**`

Scenarios that must pass:

1. **Mission upload and execute**: Upload a 3-waypoint mission; arm (SITL only); execute; land at home. Assert: mission completes; audit logged.

2. **RTH on link loss**: Simulate MQTT disconnection during mission; verify RTH triggered within 60 seconds.

3. **Battery RTH**: Simulate battery below 20%; verify immediate RTH.

4. **Fail-safe behaviors**: Verify all configured fail-safes (land on GPS loss, RTH on RC loss) trigger in SITL.

5. **Arm guard**: Attempt to arm via model-router (AI path); verify PolicyViolationError is raised; drone does not arm.

**Pass criteria**: All 5 scenarios pass. Arm guard test is mandatory (fitness function F01).

## Gate: Drone HIL (field-qualified prerequisite)

**Environment**: Real drone, outdoor test site, operator with RC kill switch  
**Trigger**: Manual trigger only; required before `field-qualified/drone-control` tag

Pre-HIL checklist:
- [ ] Drone passed QA4 hardware qualification
- [ ] SITL gate passed on same code
- [ ] Weather check: winds < 10 mph, no precipitation
- [ ] Airspace check: no NOTAMs, no manned aircraft activity
- [ ] FAA compliance verified (Part 107 or recreational rules as applicable)
- [ ] RC kill switch tested on ground

HIL test sequence:

1. **Ground system check**: All sensors, GPS lock, compass calibration. Verify RTK fix if available.

2. **Tethered hover**: Tether attached; 1m hover for 60 seconds. Verify stable hover; verify telemetry stream.

3. **Manual flight**: Remove tether; manual flight 5m AGL; verify all controls nominal; land.

4. **Supervised autonomous hover**: Arm in AUTO mode; 5m AGL hover for 30 seconds; land. Operator has RC kill switch ready.

5. **RC kill switch test**: During hover, trigger RC kill switch. Verify motor cutoff (expected crash from 1m AGL over soft surface — use tether for this test).

6. **Operator sign-off form**: Complete and attach.

**Pass criteria**: Steps 1–4 pass; step 5 verified in controlled environment. Operator sign-off recorded.

## Runbook: HIL environment setup

### Self-hosted runner setup

```bash
# Install ROS 2 Kilted on runner
sudo apt install ros-kilted-desktop

# Install Nav2
sudo apt install ros-kilted-nav2-bringup

# Install PX4 dependencies
pip install empy==3.3.4 future jsonschema numpy packaging kconfiglib

# Clone PX4 at pinned version
git clone https://github.com/PX4/PX4-Autopilot.git --branch v1.16.0
cd PX4-Autopilot
make px4_sitl gazebo-classic_iris  # Verify SITL works
```

### Runner registration

The HIL runner is registered as a GitHub Actions self-hosted runner with the `hil` label. It is only used for HIL gate jobs.

### Network setup

HIL runner must have:
- Access to the MQTT broker (can use test MQTT instance)
- Access to the orchestrator and control-api (can use local dev stack)
- ROS2 DDS domain ID isolated from production (set `ROS_DOMAIN_ID=99` for HIL tests)
