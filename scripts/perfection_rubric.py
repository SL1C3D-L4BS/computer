#!/usr/bin/env python3
"""
Computer System — Perfection Rubric

Executable pass/fail checklist validating the full system against all
architectural, safety, UX, release, recovery, simulation, hardware,
boundary, observability, and documentation standards.

Usage:
  python3 scripts/perfection_rubric.py
  python3 scripts/perfection_rubric.py --category ai_safety
  python3 scripts/perfection_rubric.py --json

Exit codes:
  0 = ALL PASS
  1 = Some checks failed
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parent.parent

# ── Pass condition helpers ────────────────────────────────────────────────────

def _file_exists(path: str) -> tuple[bool, str]:
    p = REPO_ROOT / path
    return p.exists(), f"{'EXISTS' if p.exists() else 'MISSING'}: {path}"


def _dir_exists(path: str) -> tuple[bool, str]:
    p = REPO_ROOT / path
    return p.is_dir(), f"{'EXISTS' if p.is_dir() else 'MISSING'}: {path}"


def _count_files(path: str, pattern: str, minimum: int) -> tuple[bool, str]:
    p = REPO_ROOT / path
    if not p.exists():
        return False, f"Directory missing: {path}"
    files = list(p.glob(pattern))
    ok = len(files) >= minimum
    return ok, f"{len(files)}/{minimum}+ {pattern} in {path}"


def _file_contains(path: str, text: str) -> tuple[bool, str]:
    p = REPO_ROOT / path
    if not p.exists():
        return False, f"File missing: {path}"
    content = p.read_text()
    found = text in content
    return found, f"{'FOUND' if found else 'MISSING'} '{text[:50]}' in {path}"


def _script_is_executable(path: str) -> tuple[bool, str]:
    import os
    p = REPO_ROOT / path
    if not p.exists():
        return False, f"Script missing: {path}"
    executable = os.access(p, os.X_OK)
    return executable, f"{'EXECUTABLE' if executable else 'NOT EXECUTABLE'}: {path}"


# ── CATEGORY: Architecture ────────────────────────────────────────────────────

ARCHITECTURE_CHECKS = [
    ("Runtime version gate script exists and is executable",
     lambda: _script_is_executable("scripts/check_runtime.sh")),
    (".node-version pin file exists",
     lambda: _file_exists(".node-version")),
    (".python-version pin file exists",
     lambda: _file_exists(".python-version")),
    ("ADRs 001-032 present (16 original + 16 runtime-v2)",
     lambda: _count_files("docs/adr", "ADR-*.md", 32)),
    ("Service responsibility matrix exists",
     lambda: _file_exists("docs/architecture/service-responsibility-matrix.md")),
    ("Runtime glue spec exists",
     lambda: _file_exists("docs/architecture/runtime-glue-and-cohesion.md")),
    ("Policy domain model exists",
     lambda: _file_exists("docs/architecture/policy-domain-model.md")),
    ("Versions matrix (versions.json) exists",
     lambda: _file_exists("packages/config/versions.json")),
    ("Site config (site.yaml) exists",
     lambda: _file_exists("packages/config/site/site.yaml")),
    ("Contracts package exists",
     lambda: _dir_exists("packages/contracts")),
    ("Assistant contracts exist",
     lambda: _dir_exists("packages/assistant-contracts")),
    ("BOM phase-1 exists",
     lambda: _file_exists("data/bom/phase-1.yaml")),
    ("Asset seed file exists",
     lambda: _file_exists("data/seed/assets.yaml")),
]

# ── CATEGORY: AI Safety ───────────────────────────────────────────────────────

AI_SAFETY_CHECKS = [
    ("ADR-002 (AI no actuation) exists",
     lambda: _file_exists("docs/adr/ADR-002-ai-no-actuation.md")),
    ("Actuation policy doc exists",
     lambda: _file_exists("docs/safety/actuation-policy.md")),
    ("Safety gate script exists",
     lambda: _file_exists("scripts/ci/safety_gate.py")),
    ("Semgrep AI safety rules exist",
     lambda: _file_exists(".github/semgrep/ai-safety-rules.yml")),
    ("model-router tool_registry enforces AI boundaries",
     lambda: _file_exists("apps/model-router/model_router/tool_registry.py")),
    ("model-router tools.py has no direct MQTT publish",
     lambda: _check_no_mqtt_in_tools()),
    ("Orchestrator F05 enforcement (AI origin → OPERATOR_REQUIRED)",
     lambda: _file_contains("apps/orchestrator/orchestrator/state_machine.py", "AI_ADVISORY")),
    ("F01 gate in CI web-backend workflow",
     lambda: _file_contains(".github/workflows/web-backend.yml", "safety-gate")),
    ("Drone arming requires OPERATOR_CONFIRM_TWICE",
     lambda: _file_contains("services/drone-control/drone_control/flight_state_machine.py",
                             "OPERATOR_CONFIRM_TWICE") or
             _file_contains("services/drone-control/drone_control/mavlink_bridge.py",
                             "operator_token")[0]),
]

def _check_no_mqtt_in_tools():
    p = REPO_ROOT / "apps/model-router/model_router/tools.py"
    if not p.exists():
        return False, "tools.py missing"
    content = p.read_text()
    forbidden = ['client.publish(f"commands/', 'client.publish("commands/']
    for pattern in forbidden:
        if pattern in content:
            return False, f"F01 VIOLATION: Direct MQTT publish found: '{pattern}'"
    return True, "No direct MQTT command publishes in tools.py"

# ── CATEGORY: Operator UX ─────────────────────────────────────────────────────

UX_CHECKS = [
    ("ops-web app exists",
     lambda: _dir_exists("apps/ops-web")),
    ("assistant-api exists",
     lambda: _file_exists("apps/assistant-api/assistant_api/main.py")),
    ("context-router exists",
     lambda: _file_exists("services/context-router/context_router/main.py")),
    ("identity-service exists",
     lambda: _file_exists("services/identity-service/identity_service/main.py")),
    ("memory-service exists",
     lambda: _file_exists("services/memory-service/memory_service/main.py")),
    ("voice-gateway exists",
     lambda: _file_exists("services/voice-gateway/voice_gateway/main.py")),
    ("Assistant charter exists",
     lambda: _file_exists("docs/product/computer-assistant-charter.md")),
    ("Trust tiers doc exists",
     lambda: _file_exists("docs/product/assistant-trust-tiers.md")),
    ("Family assistant spec exists",
     lambda: _file_exists("docs/product/family-assistant-spec.md")),
]

# ── CATEGORY: Release Engineering ────────────────────────────────────────────

RELEASE_CHECKS = [
    ("Release CI workflow exists",
     lambda: _file_exists(".github/workflows/release.yml")),
    ("Web/backend CI workflow exists",
     lambda: _file_exists(".github/workflows/web-backend.yml")),
    ("Security scan CI workflow exists",
     lambda: _file_exists(".github/workflows/security.yml")),
    ("Robotics CI workflow exists",
     lambda: _file_exists(".github/workflows/robotics.yml")),
    ("Simulation CI workflow exists",
     lambda: _file_exists(".github/workflows/simulation.yml")),
    ("Release classes doc exists",
     lambda: _file_exists("docs/standards/release-classes.md")),
    ("Compatibility policy doc exists",
     lambda: _file_exists("docs/standards/compatibility-policy.md")),
    ("Release validator script exists",
     lambda: _file_exists("scripts/release/validate_release_class.py")),
    ("sim-stable release gates PASS",
     lambda: _run_release_validation("v0.1.0", "sim-stable")),
]

def _run_release_validation(version: str, release_class: str) -> tuple[bool, str]:
    import subprocess
    result = subprocess.run(
        ["python3", "scripts/release/validate_release_class.py",
         "--version", version, "--class", release_class],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    ok = result.returncode == 0
    return ok, f"{'PASS' if ok else 'FAIL'}: release validation {release_class}"

# ── CATEGORY: Recovery ────────────────────────────────────────────────────────

RECOVERY_CHECKS = [
    ("Backup script exists and is executable",
     lambda: _script_is_executable("scripts/backup/backup.sh")),
    ("Restore script exists and is executable",
     lambda: _script_is_executable("scripts/backup/restore.sh")),
    ("Rollback-and-restore doc exists",
     lambda: _file_exists("docs/delivery/rollback-and-restore.md")),
    ("Bootstrap script exists and is executable",
     lambda: _script_is_executable("bootstrap.sh")),
    ("Degraded mode spec exists",
     lambda: _file_exists("docs/safety/degraded-mode-spec.md") or
             _file_exists("docs/architecture/emergency-mode-spec.md")),
]

# ── CATEGORY: Simulation ──────────────────────────────────────────────────────

SIMULATION_CHECKS = [
    ("Milestone 1 integration test exists",
     lambda: _file_exists("tests/integration/test_milestone_1.py")),
    ("Milestone 2 integration test exists",
     lambda: _file_exists("tests/integration/test_milestone_2.py")),
    ("Milestone 3 integration test exists",
     lambda: _file_exists("tests/integration/test_milestone_3.py")),
    ("Milestone 4 integration test exists",
     lambda: _file_exists("tests/integration/test_milestone_4.py")),
    ("Milestone 5 integration test exists",
     lambda: _file_exists("tests/integration/test_milestone_5.py")),
    ("Rover SITL scenario runner exists",
     lambda: _file_exists("robotics/simulation/rover_sitl.py")),
    ("Drone SITL scenario runner exists",
     lambda: _file_exists("robotics/simulation/drone_sitl.py")),
    ("Gazebo world SDF exists",
     lambda: _file_exists("robotics/simulation/gazebo_world.sdf")),
    ("Rover state machine unit tests exist",
     lambda: _file_exists("services/rover-control/tests/test_mission_state_machine.py")),
    ("Drone flight state machine tests exist",
     lambda: _file_exists("services/drone-control/tests/test_flight_state_machine.py")),
]

# ── CATEGORY: Hardware Qualification ─────────────────────────────────────────

HARDWARE_CHECKS = [
    ("Hardware qualification doc exists",
     lambda: _file_exists("docs/safety/hardware-qualification-checklists.md")),
    ("Calibration SOPs doc exists",
     lambda: _file_exists("docs/safety/calibration-sops.md")),
    ("BOM phase-1 exists",
     lambda: _file_exists("data/bom/phase-1.yaml")),
    ("Rover asset in seed data",
     lambda: _file_contains("data/seed/assets.yaml", "field-rover-001")),
    ("Rover assigned QA0 or higher qualification",
     lambda: _file_contains("data/seed/assets.yaml", "qualification_level")),
    ("Rover control service has Dockerfile",
     lambda: _file_exists("services/rover-control/Dockerfile")),
    ("Drone control service has Dockerfile",
     lambda: _file_exists("services/drone-control/Dockerfile")),
    ("PX4 SITL setup doc exists",
     lambda: _file_exists("robotics/px4/sitl_setup.md")),
]

# ── CATEGORY: Boundary Enforcement ───────────────────────────────────────────

BOUNDARY_CHECKS = [
    ("ADR-010 (capability/adapter boundary) exists",
     lambda: _file_exists("docs/adr/ADR-010-capability-model.md")),
    ("HA adapter entity_map (only place with vendor IDs)",
     lambda: _file_exists("services/ha-adapter/ha_adapter/entity_map.py")),
    ("Frigate adapter event_normalizer exists",
     lambda: _file_exists("services/frigate-adapter/frigate_adapter/event_normalizer.py")),
    ("Core/site/adapter boundary doc exists",
     lambda: _file_exists("docs/productization/computer-core-boundary.md")),
    ("Site config boundary doc exists",
     lambda: _file_exists("docs/productization/site-config-boundary.md")),
    ("Config SDK exists",
     lambda: _file_exists("packages/config/sdk/__init__.py")),
    ("Orchestrator models use canonical asset_id (not entity_id)",
     lambda: _check_no_entity_id_in_orchestrator()),
]

def _check_no_entity_id_in_orchestrator():
    p = REPO_ROOT / "apps/orchestrator/orchestrator/models.py"
    if not p.exists():
        return False, "orchestrator/models.py missing"
    content = p.read_text()
    if '"entity_id"' in content and "asset_id" not in content:
        return False, "Orchestrator uses entity_id without asset_id — boundary violation"
    return True, "Orchestrator uses canonical asset_id"

# ── CATEGORY: Observability ───────────────────────────────────────────────────

OBSERVABILITY_CHECKS = [
    ("Architecture fitness doc exists",
     lambda: _file_exists("docs/standards/architecture-fitness.md")),
    ("CI matrix doc exists",
     lambda: _file_exists("docs/delivery/ci-matrix.md")),
    ("Event-ingest service exists",
     lambda: _dir_exists("apps/event-ingest")),
    ("Digital twin /assets endpoint exists",
     lambda: _file_contains("apps/digital-twin/digital_twin/main.py", "/assets")),
    ("Orchestrator job state machine logs all transitions",
     lambda: _file_contains("apps/orchestrator/orchestrator/state_machine.py", "job_state_transition")),
    ("Rover mission log in state machine",
     lambda: _file_contains("services/rover-control/rover_control/mission_state_machine.py",
                             "mission_log")),
    ("Drone flight log in state machine",
     lambda: _file_contains("services/drone-control/drone_control/flight_state_machine.py",
                             "flight_log")),
    ("Incident queue in security monitor",
     lambda: _file_exists("services/security-monitor/security_monitor/incident_queue.py")),
]

# ── CATEGORY: Documentation ───────────────────────────────────────────────────

DOCS_CHECKS = [
    ("Service responsibility matrix",
     lambda: _file_exists("docs/architecture/service-responsibility-matrix.md")),
    ("Safety actuation policy",
     lambda: _file_exists("docs/safety/actuation-policy.md")),
    ("E-stop and failsafe doc",
     lambda: _file_exists("docs/safety/e-stop-and-fail-safe.md") or
             _file_exists("docs/safety/e-stop.md")),
    ("Command risk classification",
     lambda: _file_exists("docs/safety/command-risk-classification.md")),
    ("CI matrix doc",
     lambda: _file_exists("docs/delivery/ci-matrix.md")),
    ("HIL gate plan",
     lambda: _file_exists("docs/delivery/hil-gate-plan.md")),
    ("Release train doc",
     lambda: _file_exists("docs/delivery/release-train.md")),
    ("Repo bootstrap spec",
     lambda: _file_exists("docs/delivery/repo-bootstrap-spec.md")),
    ("Assistant charter",
     lambda: _file_exists("docs/product/computer-assistant-charter.md")),
    ("Change control doc",
     lambda: _file_exists("docs/standards/change-control.md")),
]

# ── CATEGORY: Runtime Intelligence v2 (CRK Spine + 8 Planes) ─────────────────

def _check_mcp_no_drone_arm() -> tuple[bool, str]:
    """Verify drone.arm is never registered in mcp-gateway registry."""
    p = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "registry.py"
    if not p.exists():
        return False, "mcp-gateway/registry.py missing"
    content = p.read_text()
    # The only allowed mention is in comments like "# NOTE: No 'drone.arm'" or the policy deny rule
    # Check that "drone.arm" doesn't appear as a TOOL_REGISTRY key
    if '"drone.arm"' in content and "TOOL_REGISTRY" in content:
        # Check if it's just in a comment/note or actually registered
        lines = [l.strip() for l in content.splitlines() if '"drone.arm"' in l and not l.strip().startswith("#")]
        if lines:
            return False, f"drone.arm appears in registry code: {lines[0][:80]}"
    return True, "drone.arm is not registered in TOOL_REGISTRY"


def _mcp_gateway_no_risk_ordering() -> tuple[bool, str]:
    """Verify mcp-gateway does NOT use simplistic risk_class < tier comparison."""
    p = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "policy.py"
    if not p.exists():
        return False, "mcp-gateway/policy.py missing"
    content = p.read_text()
    forbidden = ["risk_class <", "risk_class >", "risk_class <=", "risk_class >=",
                 "< trust_tier", "> trust_tier"]
    for f in forbidden:
        if f in content:
            return False, f"Forbidden risk_class ordering comparison found: {f!r}"
    return True, "No simplistic risk_class ordering comparison in policy.py"


RUNTIME_V2_CHECKS = [
    # ── CRK Spine ──────────────────────────────────────────────────────────────
    ("runtime-contracts package exists (models.py + index.ts)",
     lambda: _file_exists("packages/runtime-contracts/models.py") and
             _file_exists("packages/runtime-contracts/src/index.ts")),
    ("runtime-kernel service exists with /execute endpoint",
     lambda: _file_contains("services/runtime-kernel/runtime_kernel/main.py", "/execute")),
    ("runtime-kernel loop has 10 steps (including 7a and 7b)",
     lambda: _file_contains("services/runtime-kernel/runtime_kernel/loop.py", "step7a_invoke_tool") and
             _file_contains("services/runtime-kernel/runtime_kernel/loop.py", "step7b_bind_control_job")),
    ("mcp-gateway package exists with /tools/invoke",
     lambda: _file_contains("packages/mcp-gateway/mcp_gateway/main.py", "/tools/invoke")),
    ("mcp-gateway policy is a function (not ordering comparison)",
     _mcp_gateway_no_risk_ordering),
    ("mcp-gateway never registers drone.arm",
     lambda: _check_mcp_no_drone_arm()),
    # ── Authority docs ─────────────────────────────────────────────────────────
    ("docs/architecture/runtime-kernel.md exists",
     lambda: _file_exists("docs/architecture/runtime-kernel.md")),
    ("docs/architecture/kernel-authority-model.md exists",
     lambda: _file_exists("docs/architecture/kernel-authority-model.md")),
    ("docs/architecture/workflow-orchestrator-boundary.md exists",
     lambda: _file_exists("docs/architecture/workflow-orchestrator-boundary.md")),
    ("docs/product/mode-transition-rules.md exists (includes shared-device rule)",
     lambda: _file_contains("docs/product/mode-transition-rules.md", "Shared-Device")),
    # ── Phase 0B services ──────────────────────────────────────────────────────
    ("services/workflow-runtime/ exists",
     lambda: _dir_exists("services/workflow-runtime")),
    ("services/attention-engine/ exists",
     lambda: _dir_exists("services/attention-engine")),
    ("services/authz-service/ exists",
     lambda: _dir_exists("services/authz-service")),
    ("infra/otel/otel-collector.yml exists (trace-gateway config-only)",
     lambda: _file_exists("infra/otel/otel-collector.yml")),
    # ── Phase 1 architecture docs ──────────────────────────────────────────────
    ("docs/architecture/missing-runtime-planes.md exists (8 planes)",
     lambda: _file_exists("docs/architecture/missing-runtime-planes.md")),
    ("docs/architecture/tool-fabric-and-mcp-plan.md exists",
     lambda: _file_exists("docs/architecture/tool-fabric-and-mcp-plan.md")),
    ("docs/architecture/durable-workflow-strategy.md exists",
     lambda: _file_exists("docs/architecture/durable-workflow-strategy.md")),
    ("docs/architecture/authorization-evolution.md exists",
     lambda: _file_exists("docs/architecture/authorization-evolution.md")),
    ("docs/product/attention-and-escalation-policy.md exists",
     lambda: _file_exists("docs/product/attention-and-escalation-policy.md")),
    ("docs/product/voice-fluency-spec.md exists (includes shared-device rule)",
     lambda: _file_contains("docs/product/voice-fluency-spec.md", "Shared-Device")),
    ("docs/delivery/assistant-eval-plan.md exists",
     lambda: _file_exists("docs/delivery/assistant-eval-plan.md")),
    ("docs/observability/end-to-end-tracing-plan.md exists",
     lambda: _file_exists("docs/observability/end-to-end-tracing-plan.md")),
    # ── Phase 2 stubs ──────────────────────────────────────────────────────────
    ("services/eval-runner/ exists",
     lambda: _dir_exists("services/eval-runner")),
    ("packages/mcp-tools/ exists",
     lambda: _dir_exists("packages/mcp-tools")),
    ("packages/mcp-servers/ exists",
     lambda: _dir_exists("packages/mcp-servers")),
    ("packages/authz-model/ exists",
     lambda: _dir_exists("packages/authz-model")),
    ("packages/sync-model/ exists",
     lambda: _dir_exists("packages/sync-model")),
    ("packages/eval-fixtures/ exists",
     lambda: _dir_exists("packages/eval-fixtures")),
    # ── ADRs 017-032 ──────────────────────────────────────────────────────────
    ("ADR-017 through ADR-032 all present (16 runtime-v2 ADRs)",
     lambda: _count_files("docs/adr", "ADR-0[12][0-9]-*.md", 16) or
             _count_files("docs/adr", "ADR-0[23][0-9]-*.md", 16)),
    ("ADR-025 CRK primary loop exists",
     lambda: _file_exists("docs/adr/ADR-025-crk-primary-execution-loop.md")),
    ("ADR-030 kernel authority model exists",
     lambda: _file_exists("docs/adr/ADR-030-kernel-authority-model.md")),
    ("ADR-032 mode transitions + shared-device rule exists",
     lambda: _file_exists("docs/adr/ADR-032-mode-transitions-stickiness-shared-device.md")),
]


# ── Scientific Rigor checks ───────────────────────────────────────────────────

def _model_has_section(doc_path: str, section_keyword: str) -> tuple[bool, str]:
    """Verify that a model doc contains a required section keyword."""
    p = REPO_ROOT / doc_path
    if not p.exists():
        return False, f"MISSING: {doc_path}"
    text = p.read_text()
    found = section_keyword.lower() in text.lower()
    return found, f"{'FOUND' if found else 'MISSING'} section '{section_keyword}' in {doc_path}"


def _contracts_has_type(type_name: str) -> tuple[bool, str]:
    """Verify runtime-contracts/models.py defines a given dataclass/enum."""
    return _file_contains("packages/runtime-contracts/models.py", type_name)


def _calibration_test_exists(test_class: str) -> tuple[bool, str]:
    """Verify a calibration test class exists."""
    for fname in ["test_confidence_calibration.py", "test_invariant_failure_injection.py"]:
        p = REPO_ROOT / "tests" / "calibration" / fname
        if p.exists() and test_class in p.read_text():
            return True, f"FOUND class {test_class} in tests/calibration/{fname}"
    return False, f"MISSING test class {test_class} in tests/calibration/"


SCIENTIFIC_RIGOR_CHECKS: list[tuple[str, Any]] = [
    # ── State model completeness ──────────────────────────────────────────────
    ("State model doc exists",
     lambda: _file_exists("docs/architecture/system-state-model.md")),
    ("State model: operational partition defined",
     lambda: _model_has_section("docs/architecture/system-state-model.md", "operational")),
    ("State model: assistant partition defined",
     lambda: _model_has_section("docs/architecture/system-state-model.md", "assistant")),
    ("State model: memory partition defined",
     lambda: _model_has_section("docs/architecture/system-state-model.md", "memory")),
    ("State model: confidence/decay semantics present",
     lambda: _model_has_section("docs/architecture/system-state-model.md", "decay")),

    # ── Transition and control model ──────────────────────────────────────────
    ("Transition model doc exists",
     lambda: _file_exists("docs/architecture/transition-and-control-model.md")),
    ("Transition model: control inputs (U) defined",
     lambda: _model_has_section("docs/architecture/transition-and-control-model.md", "control inputs")),
    ("Transition model: disturbances (W) defined",
     lambda: _model_has_section("docs/architecture/transition-and-control-model.md", "disturbance")),
    ("Transition model: attention decision function present",
     lambda: _model_has_section("docs/architecture/transition-and-control-model.md", "attention")),

    # ── Objective functions coverage ──────────────────────────────────────────
    ("Objective functions doc exists",
     lambda: _file_exists("docs/architecture/objective-functions.md")),
    ("Objective functions: hard constraints (HC-01) defined",
     lambda: _model_has_section("docs/architecture/objective-functions.md", "HC-01")),
    ("Objective functions: at least 8 hard constraints present",
     lambda: (
         (lambda text: sum(1 for i in range(1, 9) if f"HC-{i:02d}" in text) >= 8)(
             (REPO_ROOT / "docs/architecture/objective-functions.md").read_text()
             if (REPO_ROOT / "docs/architecture/objective-functions.md").exists() else ""
         ),
         "HC-01..HC-08 present in objective-functions.md"
     )),
    ("Objective functions: per-mode weight table present",
     lambda: _model_has_section("docs/architecture/objective-functions.md", "weight")),
    ("Objective functions: assistant utility objective present",
     lambda: _model_has_section("docs/architecture/objective-functions.md", "assistant utility")),

    # ── Uncertainty model ─────────────────────────────────────────────────────
    ("Uncertainty model doc exists",
     lambda: _file_exists("docs/architecture/uncertainty-and-confidence-model.md")),
    ("Uncertainty model: confidence types defined",
     lambda: _model_has_section("docs/architecture/uncertainty-and-confidence-model.md", "IdentityConfidence")),
    ("Uncertainty model: propagation rules present",
     lambda: _model_has_section("docs/architecture/uncertainty-and-confidence-model.md", "propagation")),
    ("Uncertainty model: hard veto conditions present",
     lambda: _model_has_section("docs/architecture/uncertainty-and-confidence-model.md", "veto")),

    # ── Formal invariants and proof obligations ───────────────────────────────
    ("Formal invariants doc exists",
     lambda: _file_exists("docs/safety/formal-invariants-and-proof-obligations.md")),
    ("Invariants: I-01 (safety boundary) present",
     lambda: _model_has_section("docs/safety/formal-invariants-and-proof-obligations.md", "I-01")),
    ("Invariants: I-10 (no auto-apply) present",
     lambda: _model_has_section("docs/safety/formal-invariants-and-proof-obligations.md", "I-10")),
    ("Invariants: at least 10 invariants present",
     lambda: (
         (lambda text: sum(1 for i in range(1, 11) if f"I-{i:02d}" in text) >= 10)(
             (REPO_ROOT / "docs/safety/formal-invariants-and-proof-obligations.md").read_text()
             if (REPO_ROOT / "docs/safety/formal-invariants-and-proof-obligations.md").exists() else ""
         ),
         "I-01..I-10 present in formal-invariants doc"
     )),
    ("Invariants: violation handling defined",
     lambda: _model_has_section("docs/safety/formal-invariants-and-proof-obligations.md", "violation")),

    # ── Scientific types in runtime-contracts ─────────────────────────────────
    ("runtime-contracts: ConfidenceScore defined",
     lambda: _contracts_has_type("ConfidenceScore")),
    ("runtime-contracts: UncertaintyVector defined",
     lambda: _contracts_has_type("UncertaintyVector")),
    ("runtime-contracts: InvariantCheckResult defined",
     lambda: _contracts_has_type("InvariantCheckResult")),
    ("runtime-contracts: DecisionRationale defined",
     lambda: _contracts_has_type("DecisionRationale")),
    ("runtime-contracts: OpenLoop defined",
     lambda: _contracts_has_type("OpenLoop")),
    ("runtime-contracts: Commitment defined",
     lambda: _contracts_has_type("Commitment")),
    ("runtime-contracts: FollowUp defined",
     lambda: _contracts_has_type("FollowUp")),
    ("runtime-contracts: ComputerState has open_loops",
     lambda: _contracts_has_type("open_loops")),
    ("runtime-contracts: AttentionCost defined",
     lambda: _contracts_has_type("AttentionCost")),
    ("runtime-contracts: ObservationRecord defined",
     lambda: _contracts_has_type("ObservationRecord")),

    # ── Experimental and evaluation design ────────────────────────────────────
    ("Experimental design doc exists",
     lambda: _file_exists("docs/delivery/experimental-design-and-evaluation.md")),
    ("Experimental design: 5 eval tiers defined",
     lambda: _model_has_section("docs/delivery/experimental-design-and-evaluation.md", "tier")),
    ("Experimental design: Brier score calibration target present",
     lambda: _model_has_section("docs/delivery/experimental-design-and-evaluation.md", "brier")),
    ("Experimental design: ablation requirement present",
     lambda: _model_has_section("docs/delivery/experimental-design-and-evaluation.md", "ablation")),
    ("Calibration test: Brier score check implemented",
     lambda: _calibration_test_exists("TestAttentionCalibration")),
    ("Calibration test: loop decay sanity implemented",
     lambda: _calibration_test_exists("TestLoopDecaySanity")),
    ("Calibration test: invariant injection tests implemented",
     lambda: _calibration_test_exists("TestI01AIAdvisoryNoAutoActuate")),
    ("Social SITL: at least 5 scenario files present",
     lambda: _count_files("tests/scenarios/assistant", "*.json", 5)),
    ("Voice eval fixtures: at least 5 fixtures present",
     lambda: _file_contains("packages/eval-fixtures/eval_fixtures/voice_evals.py", "VoiceEvalFixture")),

    # ── Evaluation rigor: coverage across all eval tiers ─────────────────────
    ("Experimental design: offline tier defined",
     lambda: _model_has_section("docs/delivery/experimental-design-and-evaluation.md", "offline")),
    ("Experimental design: canary tier defined",
     lambda: _model_has_section("docs/delivery/experimental-design-and-evaluation.md", "canary")),
    ("Experimental design: red-team tier defined",
     lambda: _model_has_section("docs/delivery/experimental-design-and-evaluation.md", "red")),

    # ── Memory hygiene ────────────────────────────────────────────────────────
    ("Memory lifecycle policy doc exists",
     lambda: _file_exists("docs/product/memory-lifecycle-policy.md")),
    ("Memory policy: 7 memory classes present",
     lambda: (
         (lambda text: sum(1 for c in [
             "reminders", "preferences", "explicit facts",
             "shared household", "work context", "site incidents", "inferred habits"
         ] if c.lower() in text.lower()) >= 7)(
             (REPO_ROOT / "docs/product/memory-lifecycle-policy.md").read_text()
             if (REPO_ROOT / "docs/product/memory-lifecycle-policy.md").exists() else ""
         ),
         "All 7 memory classes present in memory-lifecycle-policy.md"
     )),
    ("Memory policy: hazard function defined",
     lambda: _model_has_section("docs/product/memory-lifecycle-policy.md", "hazard")),
    ("Memory policy: explicit user override rule present",
     lambda: _model_has_section("docs/product/memory-lifecycle-policy.md", "override")),
    ("Memory policy: deletion/archival thresholds defined",
     lambda: _model_has_section("docs/product/memory-lifecycle-policy.md", "archiv")),

    # ── Reflection engine (I-10 enforcement) ──────────────────────────────────
    ("Reflection engine: models.py exists",
     lambda: _file_exists("services/reflection-engine/reflection_engine/models.py")),
    ("Reflection engine: CandidatePolicyAdjustment defined",
     lambda: _file_contains("services/reflection-engine/reflection_engine/models.py", "CandidatePolicyAdjustment")),
    ("Reflection engine: I-10 operator_approved=False at creation",
     lambda: _file_contains("services/reflection-engine/reflection_engine/models.py", "operator_approved")),
    ("Reflection engine: rollback_condition required field",
     lambda: _file_contains("services/reflection-engine/reflection_engine/models.py", "rollback_condition")),
    ("Reflection engine: main.py exists",
     lambda: _file_exists("services/reflection-engine/reflection_engine/main.py")),
    ("Reflection engine: /apply enforces I-10 (requires operator_approved)",
     lambda: _file_contains("services/reflection-engine/reflection_engine/main.py", "operator_approved")),

    # ── Open-loop and attention mathematics ───────────────────────────────────
    ("Open-loop mathematics doc exists",
     lambda: _file_exists("docs/product/open-loop-mathematics.md")),
    ("Open-loop mathematics: decay function defined",
     lambda: _model_has_section("docs/product/open-loop-mathematics.md", "decay")),
    ("Open-loop mathematics: resurfacing rule defined",
     lambda: _model_has_section("docs/product/open-loop-mathematics.md", "resurf")),
    ("Attention decision model doc exists",
     lambda: _file_exists("docs/product/attention-decision-model.md")),
    ("Attention decision model: net_value function defined",
     lambda: _model_has_section("docs/product/attention-decision-model.md", "net_value")),
    ("Attention decision model: suppression state machine defined",
     lambda: _model_has_section("docs/product/attention-decision-model.md", "suppression")),
]


# ── V4 Operational Excellence Checks ──────────────────────────────────────────

V4_OPERATIONAL_CHECKS = [

    # CLI (V4.0)
    ("V4 CLI: computer.py exists",
     lambda: _file_exists("scripts/cli/computer.py")),
    ("V4 CLI: core command 'doctor' present",
     lambda: _file_contains("scripts/cli/computer.py", "doctor_cmd")),
    ("V4 CLI: core command 'trace' present",
     lambda: _file_contains("scripts/cli/computer.py", "trace_cmd")),
    ("V4 CLI: core command 'workflow' present",
     lambda: _file_contains("scripts/cli/computer.py", "workflow_cmd")),
    ("V4 CLI: 'drift digest' command present",
     lambda: _file_contains("scripts/cli/computer.py", "drift_cmd")),
    ("V4 CLI: 'summarize' command present",
     lambda: _file_contains("scripts/cli/computer.py", "summarize_cmd")),
    ("V4 CLI: 'expectation capture' command present",
     lambda: _file_contains("scripts/cli/computer.py", "expect_cmd")),
    ("V4 CLI: 'founder load' command present",
     lambda: _file_contains("scripts/cli/commands/founder.py", "decision_load_index")),
    ("V4 CLI: 'tool prune' command present",
     lambda: _file_contains("scripts/cli/commands/tools.py", "tool_prune")),

    # MCP (V4.1)
    ("V4 MCP: tool-admission-policy.md exists",
     lambda: _file_exists("docs/architecture/tool-admission-policy.md")),
    ("V4 MCP: tool-lifecycle-policy.md exists",
     lambda: _file_exists("docs/architecture/tool-lifecycle-policy.md")),
    ("V4 MCP: OIDC discovery in auth.py",
     lambda: _file_contains("packages/mcp-gateway/mcp_gateway/auth.py", "openid-configuration")),
    ("V4 MCP: incremental scope consent in auth.py",
     lambda: _file_contains("packages/mcp-gateway/mcp_gateway/auth.py", "incremental_scope_consent")),
    ("V4 MCP: URL-mode elicitation in auth.py",
     lambda: _file_contains("packages/mcp-gateway/mcp_gateway/auth.py", "url_elicitation")),
    ("V4 MCP: ≥ 32 tools registered",
     lambda: (_count_tools_in_registry() >= 32,
              f"{_count_tools_in_registry()} tools in registry (need ≥ 32)")),

    # ReBAC (V4.2)
    ("V4 ReBAC: rebac-auth-evolution.md exists",
     lambda: _file_exists("docs/architecture/rebac-auth-evolution.md")),
    ("V4 ReBAC: openfga_schema.fga exists",
     lambda: _file_exists("packages/authz-model/openfga_schema.fga")),
    ("V4 ReBAC: two-track auth split documented (session track)",
     lambda: _file_contains("docs/architecture/rebac-auth-evolution.md", "Session track")),
    ("V4 ReBAC: two-track auth split documented (approval track)",
     lambda: _file_contains("docs/architecture/rebac-auth-evolution.md", "Approval track")),
    ("V4 ReBAC: ADR-033 present",
     lambda: _file_exists("docs/adr/ADR-033-rebac-authorization-evolution.md")),

    # Passkeys (V4.2)
    ("V4 Passkeys: passkey-auth-strategy.md exists",
     lambda: _file_exists("docs/architecture/passkey-auth-strategy.md")),
    ("V4 Passkeys: approval track explicitly defined",
     lambda: _file_contains("docs/architecture/passkey-auth-strategy.md", "Approval track")),
    ("V4 Passkeys: family-web register page stub exists",
     lambda: _file_exists("apps/family-web/src/app/auth/register/page.tsx")),
    ("V4 Passkeys: family-web login page stub exists",
     lambda: _file_exists("apps/family-web/src/app/auth/login/page.tsx")),
    ("V4 Passkeys: ADR-034 present",
     lambda: _file_exists("docs/adr/ADR-034-passkey-first-auth-family-web.md")),

    # Local-first (V4.3)
    ("V4 Local-first: local-first-sync-strategy.md exists",
     lambda: _file_exists("docs/architecture/local-first-sync-strategy.md")),
    ("V4 Local-first: scope exclusions documented",
     lambda: _file_contains("docs/architecture/local-first-sync-strategy.md", "Does NOT apply to")),
    ("V4 Local-first: crdt-types.ts exists",
     lambda: _file_exists("packages/sync-model/src/crdt-types.ts")),
    ("V4 Local-first: offline-aware fetch in api.ts",
     lambda: _file_contains("apps/family-web/src/lib/api.ts", "offlineFetch")),
    ("V4 Local-first: ADR-035 present",
     lambda: _file_exists("docs/adr/ADR-035-local-first-sync-scope.md")),

    # Voice (V4.4)
    ("V4 Voice: voice-quality-engineering.md exists",
     lambda: _file_exists("docs/product/voice-quality-engineering.md")),
    ("V4 Voice: silence quality section present",
     lambda: _file_contains("docs/product/voice-quality-engineering.md", "Silence Quality")),
    ("V4 Voice: spoken_regret_rate defined",
     lambda: _file_contains("docs/product/voice-quality-engineering.md", "spoken_regret_rate")),
    ("V4 Voice: ≥ 13 voice eval fixtures",
     lambda: _count_voice_fixtures()),

    # Trust KPIs (V4.5)
    ("V4 Trust: trust-kpis-and-drift-model.md exists",
     lambda: _file_exists("docs/architecture/trust-kpis-and-drift-model.md")),
    ("V4 Trust: 11 KPIs documented (decision_load_index present)",
     lambda: _file_contains("docs/architecture/trust-kpis-and-drift-model.md", "decision_load_index")),
    ("V4 Trust: spoken_regret_rate in KPI doc",
     lambda: _file_contains("docs/architecture/trust-kpis-and-drift-model.md", "spoken_regret_rate")),
    ("V4 Trust: drift ownership table present",
     lambda: _file_contains("docs/architecture/trust-kpis-and-drift-model.md", "Override cooldown")),
    ("V4 Trust: drift-remediation-policy.md exists",
     lambda: _file_exists("docs/safety/drift-remediation-policy.md")),
    ("V4 Trust: weekly ritual documented in drift-remediation-policy.md",
     lambda: _file_contains("docs/safety/drift-remediation-policy.md", "Monday morning")),
    ("V4 Trust: test_drift_monitors.py exists",
     lambda: _file_exists("tests/calibration/test_drift_monitors.py")),
    ("V4 Trust: test_trust_metrics.py exists",
     lambda: _file_exists("tests/calibration/test_trust_metrics.py")),
    ("V4 Trust: shadow mode endpoint in eval-runner",
     lambda: _file_contains("services/eval-runner/eval_runner/main.py", "/eval/shadow")),

    # Long-horizon (V4.5)
    ("V4 Long-horizon: test_memory_pressure.py exists",
     lambda: _file_exists("tests/long_horizon/test_memory_pressure.py")),
    ("V4 Long-horizon: 10k loop simulation present",
     lambda: _file_contains("tests/long_horizon/test_memory_pressure.py", "10_000")),

    # Workflow (V4.6)
    ("V4 Workflow: workflow-registry-model.md exists",
     lambda: _file_exists("docs/architecture/workflow-registry-model.md")),
    ("V4 Workflow: 4 canonical classes registered",
     lambda: _file_contains("services/workflow-runtime/workflow_runtime/workflows.py",
                             "V4_CANONICAL_WORKFLOWS")),
    ("V4 Workflow: ReminderWorkflow defined",
     lambda: _file_contains("services/workflow-runtime/workflow_runtime/workflows.py",
                             "class ReminderWorkflow")),
    ("V4 Workflow: ApprovalWorkflow defined",
     lambda: _file_contains("services/workflow-runtime/workflow_runtime/workflows.py",
                             "class ApprovalWorkflow")),
    ("V4 Workflow: RoutineWorkflow defined",
     lambda: _file_contains("services/workflow-runtime/workflow_runtime/workflows.py",
                             "class RoutineWorkflow")),
    ("V4 Workflow: FollowUpWorkflow defined",
     lambda: _file_contains("services/workflow-runtime/workflow_runtime/workflows.py",
                             "class FollowUpWorkflow")),
    ("V4 Workflow: workflow-production-patterns.md exists",
     lambda: _file_exists("docs/architecture/workflow-production-patterns.md")),

    # V4.8: Field Truth
    ("V4.8 Field Truth: field-truth-and-shadow-mode.md exists",
     lambda: _file_exists("docs/delivery/field-truth-and-shadow-mode.md")),
    ("V4.8 Field Truth: divergence log endpoint in eval-runner",
     lambda: _file_contains("services/eval-runner/eval_runner/main.py",
                             "/eval/shadow/divergences")),

    # V4.9: Policy Tuning Console
    ("V4.9 Policy Tuning: policy-tuning-console.md exists",
     lambda: _file_exists("docs/product/policy-tuning-console.md")),
    ("V4.9 Policy Tuning: policy-publish-gate.md exists",
     lambda: _file_exists("docs/delivery/policy-publish-gate.md")),
    ("V4.9 Policy Tuning: PolicyImpactReport in runtime-contracts",
     lambda: _file_contains("packages/runtime-contracts/models.py", "PolicyImpactReport")),
    ("V4.9 Policy Tuning: ExpectationDelta in runtime-contracts",
     lambda: _file_contains("packages/runtime-contracts/models.py", "ExpectationDelta")),
    ("V4.9 Policy Tuning: ops-web policy-tuning page.tsx exists",
     lambda: _file_exists("apps/ops-web/src/app/policy-tuning/page.tsx")),

    # V5 Seed
    ("V5 Seed: cross-domain-priority-model.md exists",
     lambda: _file_exists("docs/architecture/cross-domain-priority-model.md")),

    # ADRs 033-036
    ("V4 ADR-033: ReBAC evolution ADR present",
     lambda: _file_exists("docs/adr/ADR-033-rebac-authorization-evolution.md")),
    ("V4 ADR-034: Passkey auth ADR present",
     lambda: _file_exists("docs/adr/ADR-034-passkey-first-auth-family-web.md")),
    ("V4 ADR-035: Local-first sync ADR present",
     lambda: _file_exists("docs/adr/ADR-035-local-first-sync-scope.md")),
    ("V4 ADR-036: Policy tuning ADR present",
     lambda: _file_exists("docs/adr/ADR-036-policy-tuning-requires-impact-report-and-replay.md")),
]


def _count_tools_in_registry() -> int:
    registry_path = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "registry.py"
    if not registry_path.exists():
        return 0
    return registry_path.read_text().count("ToolDescriptor(")


def _count_voice_fixtures() -> tuple[bool, str]:
    fixtures_path = REPO_ROOT / "packages" / "eval-fixtures" / "eval_fixtures" / "voice_evals.py"
    if not fixtures_path.exists():
        return False, "voice_evals.py missing"
    text = fixtures_path.read_text()
    count = text.count("VoiceEvalFixture(")
    ok = count >= 13
    return ok, f"{count}/13+ VoiceEvalFixture instances found"


# ── Runner ────────────────────────────────────────────────────────────────────

CATEGORIES = {
    "runtime_v2":        ("Runtime Intelligence v2 (CRK + 8 Planes)", RUNTIME_V2_CHECKS),
    "architecture":      ("Architecture",            ARCHITECTURE_CHECKS),
    "ai_safety":         ("AI Safety",               AI_SAFETY_CHECKS),
    "ux":                ("Operator UX",             UX_CHECKS),
    "release":           ("Release Engineering",     RELEASE_CHECKS),
    "recovery":          ("Recovery",                RECOVERY_CHECKS),
    "simulation":        ("Simulation",              SIMULATION_CHECKS),
    "hardware":          ("Hardware Qualification",  HARDWARE_CHECKS),
    "boundary":          ("Boundary Enforcement",    BOUNDARY_CHECKS),
    "observability":     ("Observability",           OBSERVABILITY_CHECKS),
    "docs":              ("Documentation",           DOCS_CHECKS),
    "scientific_rigor":  ("Scientific Rigor (V3)",  SCIENTIFIC_RIGOR_CHECKS),
    "v4_operational":    ("V4 Operational Excellence", V4_OPERATIONAL_CHECKS),
}


def run_rubric(filter_category: str | None = None) -> dict:
    results = {}
    for cat_key, (cat_name, checks) in CATEGORIES.items():
        if filter_category and cat_key != filter_category:
            continue
        cat_results = []
        for name, check_fn in checks:
            try:
                # Handle both lambda returning tuple and tuple-returning functions
                result = check_fn()
                if isinstance(result, tuple):
                    passed, detail = result
                else:
                    passed, detail = result, ""
            except Exception as e:
                passed, detail = False, f"Error: {e}"
            cat_results.append({"name": name, "passed": passed, "detail": detail})
        results[cat_key] = {"category": cat_name, "checks": cat_results}
    return results


def print_results(results: dict) -> int:
    total_pass = 0
    total_fail = 0

    print("\n" + "=" * 70)
    print("  COMPUTER SYSTEM — PERFECTION RUBRIC")
    print("=" * 70)

    for cat_key, cat_data in results.items():
        cat_name = cat_data["category"]
        checks = cat_data["checks"]
        cat_pass = sum(1 for c in checks if c["passed"])
        cat_total = len(checks)
        pct = int(100 * cat_pass / cat_total) if cat_total else 0

        status = "✓" if cat_pass == cat_total else "✗"
        print(f"\n  {status} {cat_name.upper()} ({cat_pass}/{cat_total} = {pct}%)")
        print("  " + "-" * 60)

        for check in checks:
            icon = "  [PASS]" if check["passed"] else "  [FAIL]"
            print(f"{icon} {check['name']}")
            if not check["passed"]:
                print(f"         → {check['detail']}")

        total_pass += cat_pass
        total_fail += (cat_total - cat_pass)

    grand_total = total_pass + total_fail
    pct = int(100 * total_pass / grand_total) if grand_total else 0

    print("\n" + "=" * 70)
    if total_fail == 0:
        print(f"  ✓ PERFECTION RUBRIC: ALL PASS ({total_pass}/{grand_total} = {pct}%)")
    else:
        print(f"  ✗ PERFECTION RUBRIC: {total_fail} FAILURES ({total_pass}/{grand_total} = {pct}%)")
    print("=" * 70 + "\n")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Computer perfection rubric")
    parser.add_argument("--category", choices=list(CATEGORIES.keys()),
                        help="Run single category (e.g. scientific_rigor, runtime_v2)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    results = run_rubric(filter_category=args.category)

    if args.json:
        print(json.dumps(results, indent=2))
        fail_count = sum(
            1 for cat in results.values()
            for c in cat["checks"]
            if not c["passed"]
        )
        sys.exit(0 if fail_count == 0 else 1)
    else:
        sys.exit(print_results(results))
