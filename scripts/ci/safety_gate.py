#!/usr/bin/env python3
"""
CI Safety Gate — Architecture Fitness Function F01.

Verifies that no code in AI paths (model-router, assistant-api, context-router)
publishes to MQTT command_request or command_ack topics.

Usage: python scripts/ci/safety_gate.py
Exit 0: pass; Exit 1: fail
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]

# Paths where AI code lives — must never publish to MQTT command topics
AI_PATHS = [
    ROOT / "apps" / "model-router",
    ROOT / "apps" / "assistant-api",
    ROOT / "services" / "context-router",
]

# Patterns that indicate MQTT command publishing
FORBIDDEN_PATTERNS = [
    r'publish\s*\(.*command_request',
    r'publish\s*\(.*command_ack',
    r'\.publish\s*\(.*command',
    r'mqtt.*publish.*command_request',
    r'client\.publish.*command',
]

violations: list[str] = []

for ai_path in AI_PATHS:
    if not ai_path.exists():
        continue  # Service not yet scaffolded
    for py_file in ai_path.rglob("*.py"):
        content = py_file.read_text()
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, content, re.IGNORECASE):
                violations.append(f"F01 VIOLATION: {py_file} matches pattern: {pattern}")

if violations:
    print("SAFETY GATE FAILED — Architecture Fitness Function F01 violated:")
    for v in violations:
        print(f"  {v}")
    print()
    print("AI paths must never publish to MQTT command_request or command_ack topics.")
    print("Permitted path: model-router → assistant-tools → control-api → orchestrator → MQTT")
    sys.exit(1)

print("Safety gate passed.")
print("  F01: No MQTT command publish from AI paths ✓")
sys.exit(0)
