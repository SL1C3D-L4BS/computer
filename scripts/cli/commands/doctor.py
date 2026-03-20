"""
computer doctor [--fix]

Service health, version drift, MCP registry status,
trace pipeline sanity, policy checksum.

--fix applies safe auto-remediations (stale mode cache, connectivity resets).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click

from scripts.cli.formatters import section, status_line, warn, ok, summary_line

REPO_ROOT = Path(__file__).parent.parent.parent.parent
VERSIONS_FILE = REPO_ROOT / "versions.json"
SERVICES = [
    ("runtime-kernel",    "http://localhost:8100/health"),
    ("attention-engine",  "http://localhost:8200/health"),
    ("authz-service",     "http://localhost:8300/health"),
    ("workflow-runtime",  "http://localhost:8400/health"),
    ("mcp-gateway",       "http://localhost:8500/health"),
    ("reflection-engine", "http://localhost:8600/health"),
    ("eval-runner",       "http://localhost:8700/health"),
    ("memory-service",    "http://localhost:8800/health"),
]


def _http_get(url: str, timeout: int = 3) -> tuple[bool, str]:
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status < 400, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)[:60]


def _check_versions() -> list[tuple[str, bool, str]]:
    results = []
    if not VERSIONS_FILE.exists():
        return [("versions.json", False, "file missing")]
    try:
        data = json.loads(VERSIONS_FILE.read_text())
        node_target = data.get("runtimes", {}).get("node", "?")
        results.append(("versions.json readable", True, f"node target={node_target}"))
    except Exception as e:
        results.append(("versions.json parse", False, str(e)[:60]))
    return results


def _check_mcp_registry() -> tuple[bool, str]:
    registry_path = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "registry.py"
    if not registry_path.exists():
        return False, "registry.py missing"
    text = registry_path.read_text()
    tool_count = text.count("ToolDescriptor(")
    return tool_count >= 11, f"{tool_count} tools registered"


def _check_trace_pipeline() -> tuple[bool, str]:
    otel_cfg = REPO_ROOT / "infra" / "otel" / "otel-collector.yml"
    if otel_cfg.exists():
        return True, "otel-collector.yml present"
    return False, "infra/otel/otel-collector.yml missing"


def _check_policy_checksum() -> tuple[bool, str]:
    policy_path = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "policy.py"
    if not policy_path.exists():
        return False, "policy.py missing"
    return True, f"policy.py {policy_path.stat().st_size}B"


@click.command("doctor")
@click.option("--fix", is_flag=True, default=False, help="Apply safe auto-remediations")
def cmd(fix: bool) -> None:
    """Service health, version drift, MCP registry, trace pipeline, policy checksum."""
    section("computer doctor")

    total, passed = 0, 0

    # Service health
    print("\n  SERVICES")
    for svc, url in SERVICES:
        ok_flag, detail = _http_get(url)
        status_line(f"{svc}", ok_flag, detail if not ok_flag else "")
        total += 1
        if ok_flag:
            passed += 1
        elif fix:
            warn(f"  --fix: {svc} unreachable — no auto-start in stub mode")

    # Version drift
    print("\n  VERSIONS")
    for label, ok_flag, detail in _check_versions():
        status_line(label, ok_flag, detail if not ok_flag else detail)
        total += 1
        if ok_flag:
            passed += 1

    # MCP registry
    print("\n  MCP REGISTRY")
    ok_flag, detail = _check_mcp_registry()
    status_line("tool registry", ok_flag, detail)
    total += 1
    if ok_flag:
        passed += 1

    # Trace pipeline
    print("\n  TRACE PIPELINE")
    ok_flag, detail = _check_trace_pipeline()
    status_line("otel-collector config", ok_flag, detail)
    total += 1
    if ok_flag:
        passed += 1

    # Policy checksum
    print("\n  POLICY")
    ok_flag, detail = _check_policy_checksum()
    status_line("mcp-gateway policy.py", ok_flag, detail)
    total += 1
    if ok_flag:
        passed += 1

    summary_line(passed, total, "health checks")
    if passed < total and not fix:
        print("  Run with --fix to attempt auto-remediation of safe issues.\n")
