#!/usr/bin/env python3
"""
Release class validation script.

Validates that a release meets the criteria for its declared release class.
Release classes (from docs/standards/release-classes.md):
  - dev        : Development only — no field use
  - sim-stable : Simulation validated — no hardware
  - field-qualified : Full qualification — hardware permitted

Usage:
  python scripts/release/validate_release_class.py --version v1.2.3 --class sim-stable
  python scripts/release/validate_release_class.py --version v2.0.0 --class field-qualified

Exit codes:
  0 = PASS
  1 = FAIL
  2 = UNKNOWN release class
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent


def check_version_format(version: str) -> tuple[bool, str]:
    """Validate semver format: vX.Y.Z or vX.Y.Z-rc.N"""
    pattern = r"^v\d+\.\d+\.\d+(-rc\.\d+)?$"
    if re.match(pattern, version):
        return True, "OK"
    return False, f"Invalid version format: {version} (expected vX.Y.Z or vX.Y.Z-rc.N)"


def check_versions_file_exists() -> tuple[bool, str]:
    """Verify machine-readable versions matrix exists."""
    vf = REPO_ROOT / "packages" / "config" / "versions.json"
    if vf.exists():
        try:
            data = json.loads(vf.read_text())
            # Supports both flat {"node": ...} and nested {"runtimes": {"node": ...}}
            runtimes = data.get("runtimes", data)
            pkg_managers = data.get("package_managers", data)
            required = [
                ("node", runtimes),
                ("python", runtimes),
                ("pnpm", pkg_managers),
            ]
            missing = [k for k, d in required if k not in d]
            if missing:
                return False, f"versions.json missing keys: {missing}"
            return True, f"versions.json OK ({len(data)} top-level sections)"
        except json.JSONDecodeError as e:
            return False, f"versions.json parse error: {e}"
    return False, "packages/config/versions.json not found"


def check_adrs_exist() -> tuple[bool, str]:
    """Verify required ADRs are present."""
    # Support both docs/adr/ and docs/architecture/decisions/
    for adr_dir in [
        REPO_ROOT / "docs" / "adr",
        REPO_ROOT / "docs" / "architecture" / "decisions",
    ]:
        if adr_dir.exists():
            adrs = list(adr_dir.glob("ADR-*.md"))
            if len(adrs) >= 7:
                return True, f"{len(adrs)} ADRs present in {adr_dir.relative_to(REPO_ROOT)}"
    return False, "ADR directory not found or fewer than 7 ADRs"


def check_contracts_schema_exist() -> tuple[bool, str]:
    """Verify contract schemas are present."""
    schema_dirs = [
        REPO_ROOT / "packages" / "contracts",
        REPO_ROOT / "packages" / "assistant-contracts",
    ]
    for d in schema_dirs:
        if not d.exists():
            return False, f"Contracts directory not found: {d}"
    return True, "Contracts directories OK"


def check_safety_docs_exist() -> tuple[bool, str]:
    """Verify safety documentation present."""
    required_docs = [
        "docs/safety/actuation-policy.md",
        "docs/safety/command-risk-classification.md",
        "docs/standards/architecture-fitness.md",
    ]
    missing = [d for d in required_docs if not (REPO_ROOT / d).exists()]
    if missing:
        return False, f"Missing safety docs: {missing}"
    return True, "Safety docs OK"


def check_ci_workflows_exist() -> tuple[bool, str]:
    """Verify required CI workflows are present."""
    required = [
        ".github/workflows/web-backend.yml",
        ".github/workflows/security.yml",
        ".github/workflows/release.yml",
        ".github/workflows/robotics.yml",
    ]
    missing = [w for w in required if not (REPO_ROOT / w).exists()]
    if missing:
        return False, f"Missing CI workflows: {missing}"
    return True, "CI workflows OK"


def check_bootstrap_script() -> tuple[bool, str]:
    """Verify bootstrap.sh is present and executable."""
    bs = REPO_ROOT / "bootstrap.sh"
    if not bs.exists():
        return False, "bootstrap.sh not found"
    if not os.access(bs, os.X_OK):
        return False, "bootstrap.sh not executable"
    return True, "bootstrap.sh OK"


def check_simulation_tests_exist() -> tuple[bool, str]:
    """Verify simulation/integration tests are present."""
    test_files = list((REPO_ROOT / "tests" / "integration").glob("test_milestone_*.py"))
    if not test_files:
        return False, "No milestone integration tests found"
    return True, f"{len(test_files)} milestone test files"


def check_hardware_qualification(release_class: str) -> tuple[bool, str]:
    """For field-qualified releases, verify hardware qualification docs exist."""
    if release_class != "field-qualified":
        return True, "N/A (not field-qualified)"
    hq = REPO_ROOT / "docs" / "safety" / "hardware-qualification.md"
    if not hq.exists():
        return False, "Hardware qualification doc missing for field-qualified release"
    return True, "Hardware qualification doc OK"


GATES: dict[str, list] = {
    "dev": [
        check_version_format,
        check_versions_file_exists,
        check_bootstrap_script,
    ],
    "sim-stable": [
        check_version_format,
        check_versions_file_exists,
        check_adrs_exist,
        check_contracts_schema_exist,
        check_safety_docs_exist,
        check_ci_workflows_exist,
        check_bootstrap_script,
        check_simulation_tests_exist,
    ],
    "field-qualified": [
        check_version_format,
        check_versions_file_exists,
        check_adrs_exist,
        check_contracts_schema_exist,
        check_safety_docs_exist,
        check_ci_workflows_exist,
        check_bootstrap_script,
        check_simulation_tests_exist,
        lambda v: check_hardware_qualification("field-qualified"),
    ],
}


def run_validation(version: str, release_class: str) -> int:
    if release_class not in GATES:
        print(f"UNKNOWN release class: {release_class}")
        print(f"Valid classes: {list(GATES.keys())}")
        return 2

    print(f"\n{'='*60}")
    print(f"Release Class Validation")
    print(f"  Version: {version}")
    print(f"  Class:   {release_class}")
    print(f"{'='*60}\n")

    gates = GATES[release_class]
    results = []

    for gate_fn in gates:
        try:
            if gate_fn.__name__ == "<lambda>":
                passed, message = gate_fn(version)
                name = "check_hardware_qualification"
            else:
                # Pass version to check_version_format, skip for others
                if gate_fn == check_version_format:
                    passed, message = gate_fn(version)
                else:
                    passed, message = gate_fn()
                name = gate_fn.__name__
        except Exception as e:
            passed, message = False, f"Error: {e}"
            name = getattr(gate_fn, "__name__", "unknown")

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {message}")
        results.append(passed)

    print()
    if all(results):
        print(f"✓ RELEASE VALIDATION PASSED: {version} is {release_class}")
        return 0
    else:
        failed = sum(1 for r in results if not r)
        print(f"✗ RELEASE VALIDATION FAILED: {failed}/{len(results)} checks failed")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate release class gates")
    parser.add_argument("--version", required=True, help="Version tag (e.g. v1.2.3)")
    parser.add_argument(
        "--class",
        dest="release_class",
        required=True,
        choices=["dev", "sim-stable", "field-qualified"],
        help="Release class to validate",
    )
    args = parser.parse_args()
    sys.exit(run_validation(args.version, args.release_class))
