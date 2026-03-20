# Hardware Qualification Checklists

Defines the qualification process and checklists for each hardware device class before it joins the Computer system.

## Qualification levels

| Level | Meaning | Required before |
|-------|---------|----------------|
| QA0 | Received and inventoried | BOM entry |
| QA1 | Bench tested; basic function verified | Installation |
| QA2 | Integrated and connected; software communication verified | Service activation |
| QA3 | Calibrated and tuned | Production use |
| QA4 | Field tested under real operating conditions | Autonomous operation approval |

## Checklist: Sensors (temperature, humidity, pH, EC, flow)

- [ ] QA0: Receive and inspect; verify model against BOM; record serial number in digital-twin
- [ ] QA1: Apply known reference input; verify reading within manufacturer spec (±5% or better)
- [ ] QA1: Power cycle; verify reading stable within 60 seconds
- [ ] QA2: Connect to MQTT; verify telemetry appearing on correct topic with correct asset_id
- [ ] QA2: Verify reading appears in digital-twin asset state
- [ ] QA3: Two-point calibration (if applicable); record calibration date and coefficients
- [ ] QA3: Cross-reference with reference instrument for ≥ 24 hours; verify drift < 2%
- [ ] QA4: Verify alarm/threshold triggers in orchestrator (if applicable)

## Checklist: Actuators (valves, pumps, relays)

- [ ] QA0: Receive and inspect; verify model and voltage/current rating against BOM
- [ ] QA1: Bench test: open/close or on/off under no-load; verify physical operation
- [ ] QA1: Test at rated load; verify operation within spec
- [ ] QA1: Test physical manual override (if applicable)
- [ ] QA2: Connect to MQTT and control service; issue test command; verify actuator responds
- [ ] QA2: Verify command-ack topic receives confirmation within timeout
- [ ] QA2: Verify fail-safe state on power loss (e.g., valve closes, pump stops)
- [ ] QA3: Test under realistic operating conditions (pressure, temperature, chemical exposure if applicable)
- [ ] QA3: Measure response time; verify within policy limits
- [ ] QA4: 1-week operational test; verify no unexpected state changes; verify audit log complete

## Checklist: Compute nodes (Raspberry Pi, edge servers)

- [ ] QA0: Receive and inventory; verify model, RAM, storage against BOM
- [ ] QA1: Flash OS; verify boot with current OS image from `infra/ansible/`
- [ ] QA1: Verify network connectivity (wired preferred; WiFi if necessary with documented reason)
- [ ] QA1: Verify SSH access with provisioning key
- [ ] QA2: Run Ansible provisioning playbook; verify all services start
- [ ] QA2: Verify device identity credentials installed (MQTT client cert or credentials)
- [ ] QA2: Verify health endpoint returns 200
- [ ] QA3: 48-hour burn-in under representative load; verify no thermal throttling
- [ ] QA4: Verify automatic restart after power loss (systemd service configured)

## Checklist: Rover chassis and drivetrain

- [ ] QA0: Inspect frame, motors, encoders; verify no damage in transit
- [ ] QA1: Bench test: motor rotation direction correct; encoder counts increment correctly
- [ ] QA1: Physical E-stop button functional (stops all motors immediately)
- [ ] QA2: ROS2 node bringup; verify odometry publishing on `/odom` topic
- [ ] QA2: Manual teleop test: verify forward/backward/turn commands execute correctly
- [ ] QA3: RTK GNSS calibration; verify positioning accuracy < 5cm in open sky
- [ ] QA3: IMU calibration; verify heading accuracy ± 2°
- [ ] QA3: Localization test: drive 10m grid pattern; verify localization error < 20cm
- [ ] QA4: SITL mission test: waypoint mission in Gazebo with matching environment
- [ ] QA4: First field test under direct human supervision; operator with physical E-stop in hand
- [ ] QA4: 48-hour field test with supervised missions; verify all safe-stop and RTH behaviors

## Checklist: Drone airframe and flight controller

- [ ] QA0: Inspect airframe, motors, propellers, ESCs; verify no damage
- [ ] QA1: Bench test (props off): motor rotation direction correct per PX4 motor order
- [ ] QA1: Accelerometer and magnetometer calibration in PX4
- [ ] QA1: RC calibration complete; all channels nominal
- [ ] QA2: PX4 SITL test: complete a simulated mission in Gazebo
- [ ] QA2: Verify telemetry link to ROS2 bridge via uXRCE-DDS
- [ ] QA2: Verify fail-safe behaviors in SITL (RTH on link loss, land on battery low)
- [ ] QA3: First hover test (low altitude, 1m, tethered or over soft ground); verify stable hover
- [ ] QA3: Verify RC kill switch disarms immediately
- [ ] QA3: Manual flight test: forward, backward, hover, landing
- [ ] QA4: Supervised autonomous mission (low altitude, open area, operator with RC kill switch)
- [ ] QA4: Verify job audit trail complete in orchestrator after mission

## Environmental operating envelopes

| System | Operating temperature | Humidity | Notes |
|--------|----------------------|----------|-------|
| Raspberry Pi 5 | 0°C to 50°C | 5–95% non-condensing | Thermal management required above 40°C ambient |
| Greenhouse sensors | -10°C to 70°C | 0–100% (sealed) | Must be IP65 or better |
| Outdoor actuators | -20°C to 60°C | Weatherproof required | IP67 or better |
| Rover | 0°C to 40°C | 0–80% non-condensing | Avoid mud/standing water |
| Drone | 0°C to 40°C | 0–80% non-condensing | Do not fly in rain or heavy wind |

## Spare strategy

| Component | Minimum spares | Lead time |
|-----------|---------------|-----------|
| pH probe | 2 (probes degrade) | 1 week |
| Flow meter | 1 | 2 weeks |
| Relay module | 2 | 1 week |
| Raspberry Pi 5 | 1 | 2 weeks |
| Solenoid valve | 2 | 1 week |
| Peristaltic pump tubing | 1 set | 1 week |
| Drone propeller set | 2 sets | 1 week |

Spares listed in `docs/bom/` per phase.
