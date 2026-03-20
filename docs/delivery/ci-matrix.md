# CI Matrix

Defines the CI pipeline lanes, their matrix dimensions, and trigger rules.

## Pipeline lanes

### Lane 1: Web/backend

**Scope**: ops-web, family-web, control-api, orchestrator, digital-twin, event-ingest, assistant-api, model-router, context-router, memory-service, identity-service, assistant-tools  
**Triggers**: Push to main, PR to main  
**Runner**: ubuntu-latest  

Matrix dimensions:
- Node.js: `[24]` (LTS; from versions.json)
- Python: `[3.14]` (from versions.json)

Jobs:
1. `lint` — ESLint (TS), ruff (Python)
2. `typecheck` — tsc --noEmit, mypy
3. `unit-test` — pytest (Python), jest (TS)
4. `contract-gate` — pnpm contracts:validate (verify generated code matches schemas)
5. `safety-gate` — static analysis for MQTT publish from AI paths
6. `audit-gate` — integration test: run a job, verify command_log entry exists
7. `integration-test` — docker compose up + API smoke tests

All 7 jobs must pass before merge.

### Lane 2: Control services

**Scope**: greenhouse-control, hydro-control, energy-engine, rover-control, drone-control, ha-adapter, frigate-adapter  
**Triggers**: Push to main, PR to main, path-filtered to `services/**`  
**Runner**: ubuntu-latest  

Matrix dimensions:
- Python: `[3.14]`

Jobs:
1. `lint` — ruff
2. `typecheck` — mypy
3. `unit-test` — pytest (state machine tests required)
4. `contract-gate` — verify service implements required contract interfaces
5. `safety-gate` — verify no direct MQTT publish to command topics without orchestrator dispatch

### Lane 3: Simulation

**Scope**: robotics/ros2_ws, robotics/sim, services/rover-control, services/drone-control  
**Triggers**: Manual trigger, nightly scheduled run  
**Runner**: Custom runner with ROS 2 Kilted + Gazebo installed  

Matrix dimensions:
- ROS 2: `[kilted]`
- Gazebo: `[latest-compatible]`

Jobs:
1. `ros-build` — colcon build
2. `sim-rover-mission` — Gazebo SITL: waypoint mission completes, safe-stop works, audit logged
3. `sim-drone-mission` — PX4 SITL: mission completes, RTH works, fail-safe triggers correctly
4. `robotics-gate` — All SITL scenarios pass before any robotics PR merges

### Lane 4: Hardware-in-loop (HIL)

**Scope**: Physical rover and drone hardware  
**Triggers**: Manual trigger only; required before `robotics-stable` or `field-qualified` release  
**Runner**: Self-hosted on-site runner with hardware access  

Jobs:
1. `hil-rover-teleop` — Manual teleop verification checklist
2. `hil-rover-mission` — Supervised autonomous mission: waypoints, safe-stop, RTH, audit
3. `hil-drone-hover` — Tethered hover test; fail-safe verification
4. `hil-signoff` — Operator records sign-off in release notes

### Lane 5: PX4/ROS compatibility

**Scope**: robotics/ directory  
**Triggers**: PR to `robotics/**`  
**Runner**: Custom runner with ROS 2 + PX4 build environment  

Jobs:
1. `uxrce-dds-compat` — Verify v2 client / v3 agent compatibility
2. `px4-build` — Full PX4 build for target hardware
3. `ros2-px4-bridge` — Verify ROS2 ↔ PX4 topic bridge at boot

### Lane 6: Security scan

**Scope**: All  
**Triggers**: PR to main, nightly  
**Runner**: ubuntu-latest  

Jobs:
1. `secret-scan` — trufflehog or gitleaks: no secrets in repo
2. `dependency-scan` — pip-audit (Python), npm audit (Node)
3. `sast` — semgrep rules for auth boundary tests
4. `auth-boundary-test` — Verify no unauthenticated routes on control-api

### Lane 7: Release

**Scope**: All  
**Triggers**: Release tag push (e.g., `site-stable/orchestrator/v1.2.0`)  
**Runner**: ubuntu-latest  

Jobs:
1. `verify-class-prefix` — Release tag must start with a valid release class
2. `rollback-metadata` — Release body must contain `rollback_to` field
3. `backup-verified` — Must have `backup-verified: true` attestation from backup check job
4. `release-notes` — Release notes must not be empty
5. `docker-publish` — Build and push Docker images with release tag

## Matrix summary

| Lane | Node | Python | ROS 2 | PX4 | Triggers |
|------|------|--------|-------|-----|---------|
| Web/backend | 24 LTS | 3.14 | - | - | PR + push |
| Control services | - | 3.14 | - | - | PR + push |
| Simulation | - | - | kilted | 1.16 | Manual + nightly |
| HIL | - | - | kilted | 1.16 | Manual only |
| PX4/ROS compat | - | - | kilted | 1.16 | PR to robotics/ |
| Security | - | - | - | - | PR + nightly |
| Release | - | - | - | - | Release tag |

## Required status checks (PR merge gates)

For a PR targeting main to merge, ALL of the following must pass:

- `web-backend / lint`
- `web-backend / typecheck`
- `web-backend / unit-test`
- `web-backend / contract-gate`
- `web-backend / safety-gate`
- `web-backend / audit-gate`
- `control-services / unit-test` (if path matches)
- `control-services / safety-gate` (if path matches)
- `robotics / robotics-gate` (if path matches `robotics/**` or `services/rover-control/**` or `services/drone-control/**`)
- `security / secret-scan`

No PR merges without all applicable gates passing.
