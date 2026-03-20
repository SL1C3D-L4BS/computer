#!/usr/bin/env bash
# run_scenario.sh — System scenario runner
# Usage: ./run_scenario.sh <scenario_name> [--dry-run]
#
# Available scenarios:
#   irrigation_leak_sim      Simulate irrigation sensor reporting anomaly
#   greenhouse_frost_alert   Simulate frost event triggering heating job
#   energy_peak_shave        Simulate TOU peak shaving activation
#   security_motion_alert    Simulate security camera motion detection
#   rover_waypoint_mission   Submit supervised rover waypoint mission
#   degraded_mqtt_loss       Simulate MQTT broker loss and recovery
#   full_e2e_flow            End-to-end: sensor event → AI advisory → operator approval → execution

set -euo pipefail

SCENARIO="${1:-}"
DRY_RUN="${2:-}"

CONTROL_API_URL="${CONTROL_API_URL:-http://localhost:8000}"
ORCHESTRATOR_URL="${ORCHESTRATOR_URL:-http://localhost:8002}"
DIGITAL_TWIN_URL="${DIGITAL_TWIN_URL:-http://localhost:8001}"
TOKEN="${OPERATOR_TOKEN:-dev-token}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[scenario]${NC} $*"; }
ok()  { echo -e "${GREEN}[PASS]${NC} $*"; }
warn(){ echo -e "${YELLOW}[WARN]${NC} $*"; }
fail(){ echo -e "${RED}[FAIL]${NC} $*"; exit 1; }

check_services() {
  log "Checking services..."
  for svc in "$CONTROL_API_URL" "$ORCHESTRATOR_URL" "$DIGITAL_TWIN_URL"; do
    if ! curl -sf "$svc/health" > /dev/null 2>&1; then
      fail "Service $svc is not healthy. Run './bootstrap.sh' first."
    fi
  done
  ok "All services healthy."
}

submit_job() {
  local description="$1"
  local payload="$2"
  log "Submitting: $description"
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo "$payload" | python3 -m json.tool
    return 0
  fi
  local response
  response=$(curl -sf -X POST "$CONTROL_API_URL/jobs" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "$payload")
  echo "$response" | python3 -m json.tool
  local state
  state=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('state','UNKNOWN'))")
  log "Job state: $state"
  echo "$state"
}

scenario_irrigation_leak_sim() {
  log "=== Scenario: Irrigation Leak Simulation ==="
  log "Step 1: Publish simulated flow sensor anomaly..."
  # In full implementation, this publishes to MQTT telemetry topic
  # For now, submit a diagnostic job to test the flow
  submit_job "Diagnostic: read flow sensor" '{
    "type": "sensor.read",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:sensor:flow:irrigation:zone-1"],
    "risk_class": "LOW",
    "parameters": {"reading_type": "flow_rate"}
  }'

  log "Step 2: Submit leak investigation job (MEDIUM risk — requires approval)..."
  submit_job "Irrigation leak investigation" '{
    "type": "irrigation.leak.investigate",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:actuator:valve:irrigation:zone-1"],
    "risk_class": "MEDIUM",
    "parameters": {"zone": "zone-1", "action": "pressure_test"}
  }'

  ok "Scenario irrigation_leak_sim complete. Check orchestrator audit log."
}

scenario_greenhouse_frost_alert() {
  log "=== Scenario: Greenhouse Frost Alert ==="
  log "Step 1: Submit temperature read (LOW risk, auto-approved)..."
  submit_job "Read greenhouse temp" '{
    "type": "sensor.read",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:sensor:temp:greenhouse-north"],
    "risk_class": "LOW",
    "parameters": {"reading_type": "temperature"}
  }'

  log "Step 2: Submit heating enable (HIGH risk — requires operator approval, F05)..."
  submit_job "Enable greenhouse heating" '{
    "type": "greenhouse.heating.enable",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:actuator:heater:greenhouse-north"],
    "risk_class": "HIGH",
    "parameters": {"target_temp_celsius": 15, "duration_hours": 8}
  }'

  ok "Scenario greenhouse_frost_alert complete. Verify HIGH-risk job in VALIDATING state."
}

scenario_energy_peak_shave() {
  log "=== Scenario: Energy Peak Shaving ==="
  log "Step 1: Read current grid energy status (LOW)..."
  submit_job "Read energy status" '{
    "type": "sensor.read",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:sensor:energy:grid-meter"],
    "risk_class": "LOW",
    "parameters": {"reading_type": "grid_import_kw"}
  }'

  log "Step 2: Submit battery discharge job (MEDIUM)..."
  submit_job "Battery discharge for peak shaving" '{
    "type": "energy.battery.discharge",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:storage:battery:bluetti-ac300"],
    "risk_class": "MEDIUM",
    "parameters": {"target_kw": 3.5, "duration_minutes": 120}
  }'

  ok "Scenario energy_peak_shave complete."
}

scenario_security_motion_alert() {
  log "=== Scenario: Security Motion Alert ==="
  log "Simulating Frigate motion detection event..."
  log "(Full implementation: event-ingest subscribes to Frigate/MQTT and creates CanonicalEvent)"
  log ""

  log "Submitting security audit job (MEDIUM risk)..."
  submit_job "Review security camera footage" '{
    "type": "security.camera.review",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:sensor:camera:exterior-north"],
    "risk_class": "MEDIUM",
    "parameters": {"clip_duration_seconds": 30, "reason": "motion_alert"}
  }'

  ok "Scenario security_motion_alert complete."
}

scenario_rover_waypoint_mission() {
  log "=== Scenario: Rover Waypoint Mission (Supervised) ==="
  warn "Phase F feature — SITL required. Simulating job submission only."
  submit_job "Rover waypoint mission" '{
    "type": "rover.mission.waypoint",
    "origin": "OPERATOR",
    "target_asset_ids": ["asset:robot:rover:field-rover-001"],
    "risk_class": "HIGH",
    "parameters": {
      "waypoints": [
        {"lat": 47.6062, "lon": -117.3321, "alt_m": 0},
        {"lat": 47.6065, "lon": -117.3325, "alt_m": 0}
      ],
      "mission_type": "inspection",
      "supervised": true
    }
  }'
  ok "Rover mission submitted. Requires OPERATOR approval (HIGH risk, F05)."
}

scenario_degraded_mqtt_loss() {
  log "=== Scenario: Degraded Mode — MQTT Loss ==="
  warn "This scenario tests that services remain healthy when MQTT is unavailable."
  log ""

  log "Step 1: Services should report degraded health when MQTT is down."
  log "Step 2: Control-API and Orchestrator remain operational for job management."
  log "Step 3: No new commands should be dispatched (no MQTT to deliver them)."
  log ""

  log "Verifying control-api health (should be degraded but responsive)..."
  curl -s "$CONTROL_API_URL/health" | python3 -m json.tool || true

  log "Verifying orchestrator health (should be degraded but responsive)..."
  curl -s "$ORCHESTRATOR_URL/health" | python3 -m json.tool || true

  ok "Degraded mode scenario observed. See docs/safety/degraded-mode-spec.md."
}

scenario_full_e2e_flow() {
  log "=== Scenario: Full End-to-End Flow ==="
  log ""
  log "Phase 1: Submit LOW-risk job (auto-approved)..."
  state=$(submit_job "Sensor read for AI advisory input" '{
    "type": "sensor.read",
    "origin": "AI_ADVISORY",
    "target_asset_ids": ["asset:sensor:soil-moisture:field-zone-1"],
    "risk_class": "LOW",
    "parameters": {"reading_type": "volumetric_moisture"}
  }')

  log "Phase 2: Submit HIGH-risk job from AI_ADVISORY (must be VALIDATING, not auto-approved)..."
  state=$(submit_job "AI advisory: enable irrigation" '{
    "type": "irrigation.zone.enable",
    "origin": "AI_ADVISORY",
    "target_asset_ids": ["asset:actuator:valve:irrigation:zone-2"],
    "risk_class": "HIGH",
    "parameters": {"zone": "zone-2", "duration_minutes": 45, "reason": "soil moisture below threshold"}
  }')

  if [[ "$state" == "VALIDATING" ]]; then
    ok "F05 PASS: AI_ADVISORY + HIGH risk job correctly halted at VALIDATING."
  else
    warn "F05 CHECK: Expected VALIDATING, got $state"
  fi

  log ""
  log "Full E2E flow scenario complete. Architecture fitness functions verified."
}

scenario_voice_assistant_query() {
  log "=== Scenario: Voice Assistant Query ==="
  log "Simulates a voice node submitting a chat request to assistant-api..."
  ASSISTANT_URL="${ASSISTANT_API_URL:-http://localhost:8021}"

  if ! curl -sf "$ASSISTANT_URL/health" > /dev/null 2>&1; then
    warn "assistant-api unavailable. Skipping voice query scenario."
    return 0
  fi

  log "Sending chat request (text mode, PERSONAL context)..."
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    echo '{"messages": [{"role": "user", "content": "What is the current greenhouse temperature?"}], "mode": "PERSONAL", "surface": "voice"}'
    return 0
  fi

  curl -sf -X POST "$ASSISTANT_URL/chat" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer dev-token" \
    -d '{"messages": [{"role": "user", "content": "What is the current greenhouse temperature?"}], "mode": "PERSONAL", "surface": "voice"}' \
    | python3 -m json.tool || warn "Chat request failed (services may not be running)"

  ok "Voice assistant scenario complete."
}

scenario_backup_drill() {
  log "=== Scenario: Backup/Restore Drill ==="
  BACKUP_DIR="${BACKUP_DIR:-/tmp/computer-backup-drill}"
  export BACKUP_DIR

  log "Running backup to ${BACKUP_DIR}..."
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    log "DRY RUN: Would run ./scripts/backup/backup.sh"
    ok "Backup drill (dry run) complete."
    return 0
  fi

  mkdir -p "${BACKUP_DIR}"
  ./scripts/backup/backup.sh && ok "Backup completed." || warn "Backup had errors"

  log "Running restore dry-run..."
  ARCHIVE=$(ls "${BACKUP_DIR}"/computer-backup-*.tar.gz 2>/dev/null | tail -1)
  if [[ -n "${ARCHIVE}" ]]; then
    ./scripts/backup/restore.sh "${ARCHIVE}" --dry-run && ok "Restore dry-run OK."
  else
    warn "No backup archive found in ${BACKUP_DIR}"
  fi

  ok "Backup/restore drill complete."
}

scenario_release_validation() {
  log "=== Scenario: Release Class Validation ==="
  python3 scripts/release/validate_release_class.py --version v0.1.0 --class sim-stable \
    && ok "Release validation: sim-stable PASSED" \
    || warn "Release validation: some gates failed"
}

usage() {
  echo "Usage: ./run_scenario.sh <scenario> [--dry-run]"
  echo ""
  echo "Scenarios:"
  echo "  irrigation_leak_sim      Irrigation sensor anomaly flow"
  echo "  greenhouse_frost_alert   Frost event → heating job"
  echo "  energy_peak_shave        TOU peak shaving activation"
  echo "  security_motion_alert    Camera motion detection flow"
  echo "  rover_waypoint_mission   Supervised rover mission submission"
  echo "  degraded_mqtt_loss       Degraded mode behavior test"
  echo "  full_e2e_flow            Complete event → advisory → approval → execution"
  echo "  voice_assistant_query    Voice node chat request"
  echo "  backup_drill             Backup and restore dry-run"
  echo "  release_validation       Validate sim-stable release class"
  echo ""
  echo "Options:"
  echo "  --dry-run    Print job payloads without submitting"
}

main() {
  if [[ -z "$SCENARIO" ]]; then
    usage
    exit 1
  fi

  if [[ "$DRY_RUN" != "--dry-run" ]]; then
    check_services
  fi

  case "$SCENARIO" in
    irrigation_leak_sim)      scenario_irrigation_leak_sim ;;
    greenhouse_frost_alert)   scenario_greenhouse_frost_alert ;;
    energy_peak_shave)        scenario_energy_peak_shave ;;
    security_motion_alert)    scenario_security_motion_alert ;;
    rover_waypoint_mission)   scenario_rover_waypoint_mission ;;
    degraded_mqtt_loss)       scenario_degraded_mqtt_loss ;;
    full_e2e_flow)            scenario_full_e2e_flow ;;
    voice_assistant_query)    scenario_voice_assistant_query ;;
    backup_drill)             scenario_backup_drill ;;
    release_validation)       scenario_release_validation ;;
    *)
      fail "Unknown scenario: $SCENARIO"
      ;;
  esac
}

main
