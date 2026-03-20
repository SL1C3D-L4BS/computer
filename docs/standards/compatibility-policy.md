# Compatibility Policy

Compatibility lanes define how each technology domain updates. Not everything updates at the same rate. Mixing update cadences causes breakage.

## Lanes

### Web lane

Components: ops-web, family-web, control-api, event-ingest, assistant-api, model-router, context-router, memory-service, identity-service, assistant-tools.

- May float **patch versions weekly**.
- Minor version updates require a passing contract-gate and integration test suite.
- Major version updates require an ADR or update to this document.

### Control lane

Components: orchestrator, greenhouse-control, hydro-control, energy-engine, digital-twin, ha-adapter, frigate-adapter.

- Floats **monthly**.
- Minor updates require passing safety-gate and state-machine tests.
- Major updates require operator sign-off and a compatibility sprint.

### Robotics lane

Components: ROS 2 (ros2_ws, Nav2, micro-ROS), PX4, Gazebo, rover-control, drone-control.

- Moves **only on scheduled compatibility sprints**.
- **ROS 2**: Locked to Kilted Kaiju LTS + Nav2 distro-matched. Do not upgrade to the next distro until it has a LTS designation.
- **PX4**: Locked to 1.16 stable until 1.17 exits alpha. Upgrade requires sim + HIL + operator signoff.
- **uXRCE-DDS**: v2 client vs v3 agent incompatibility is known; upgrade requires explicit compatibility testing.
- **Gazebo**: Pin to the ROS-compatible line per official ROS/Gazebo compatibility matrix.

### HA and Frigate lane

- **Home Assistant**: Upgrade windows are isolated; version bumps require a compatibility check against ha-adapter and the HA entity model.
- **Frigate**: Upgrades require a test of OpenVINO/TensorRT detector backend compatibility. Frigate enrichments API changes require frigate-adapter update.
- Both may update monthly, aligned with their respective release cadences.

### Model runtime lane

Components: Ollama, vLLM, model weights.

- **Ollama**: Float monthly; new versions require tool-call regression suite pass.
- **vLLM**: Float quarterly; structured output compatibility must be tested before upgrade.
- **Model weights**: Updated independently of model runtime; tool-call regression suite required for new major model versions.

## Version constraints (hard rules)

| Component | Constraint | Reason |
|-----------|-----------|--------|
| Node.js | LTS line only (currently 24 LTS) | Long-lived product; avoid chasing current |
| React | 19.2.4 or later (never 19.2.0) | Critical RSC fix landed in 19.2.1 |
| Python | 3.14.x | HA 2026.3 supports 3.14; FastAPI 0.135.x requires it |
| PostgreSQL | 18.x stable | No beta or RC in production |
| PX4 | 1.16 stable | 1.17 is alpha; no alpha in robotics lane |
| NATS | Not in v1 | Stay on MQTT + Postgres until explicit need |

## Drift detection

CI matrix runs against the pinned combination in `packages/config/versions.json`. Any PR that updates a version must also update `versions.json` and pass the affected lane's full test suite.

`packages/config/versions.json` is the single source of truth. Prose in this document is policy; the JSON file is the enforced truth.

## Compatibility sprint

A compatibility sprint is a planned sprint focused on updating one lane. It includes:
1. Review of upstream changelogs and known breaking changes.
2. Update `versions.json` in a compatibility branch.
3. Run full test suite and CI for the affected lane.
4. HIL or sim test for robotics lane updates.
5. Operator sign-off for control and robotics lanes.
6. Merge and release with changelog entry.

## Related documents

- `packages/config/versions.json` — machine-readable version pins
- `docs/standards/release-classes.md` — release class requirements
- `docs/delivery/ci-matrix.md` — CI matrix dimensions
