"""
computer tool audit
computer tool prune

Verify all registered MCP tools satisfy admission policy constraints.
List tools eligible for deprecation per tool-lifecycle-policy.md.
"""
from __future__ import annotations

import re
from pathlib import Path

import click

from scripts.cli.formatters import section, table, warn, ok, err, kv

REPO_ROOT = Path(__file__).parent.parent.parent.parent
REGISTRY_PATH = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "registry.py"
EVAL_FIXTURES_DIR = REPO_ROOT / "packages" / "eval-fixtures" / "eval_fixtures"

ADMISSION_CRITERIA = [
    "primary_mode",
    "trust_tier",
    "failure_mode",
    "eval_fixture",
    "audit_payload",
]


def _parse_tools(text: str) -> list[dict]:
    """Parse ToolDescriptor entries from registry source."""
    tools = []
    # Match ToolDescriptor blocks
    pattern = re.compile(r'ToolDescriptor\s*\((.*?)\)', re.DOTALL)
    for match in pattern.finditer(text):
        block = match.group(1)
        name_m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', block)
        mode_m = re.search(r'primary_mode\s*=\s*["\']([^"\']+)["\']', block)
        tier_m = re.search(r'trust_tier\s*=\s*["\']?(\w+)["\']?', block)
        fail_m = re.search(r'failure_mode\s*=\s*["\']([^"\']*)["\']', block)
        fixture_m = re.search(r'eval_fixture\s*=\s*["\']([^"\']*)["\']', block)
        audit_m = re.search(r'audit_payload', block)
        tools.append({
            "name": name_m.group(1) if name_m else "?",
            "primary_mode": mode_m.group(1) if mode_m else None,
            "trust_tier": tier_m.group(1) if tier_m else None,
            "failure_mode": bool(fail_m),
            "eval_fixture": bool(fixture_m),
            "audit_payload": bool(audit_m),
        })
    return tools


def _check_admission(tool: dict) -> tuple[bool, list[str]]:
    failures = []
    if not tool.get("primary_mode"):
        failures.append("missing primary_mode")
    if not tool.get("trust_tier"):
        failures.append("missing trust_tier")
    if not tool.get("failure_mode"):
        failures.append("missing failure_mode")
    if not tool.get("eval_fixture"):
        failures.append("missing eval_fixture")
    if not tool.get("audit_payload"):
        failures.append("missing audit_payload")
    return len(failures) == 0, failures


@click.group("tool")
def cmd() -> None:
    """MCP tool admission audit and lifecycle management."""


@cmd.command("audit")
def tool_audit() -> None:
    """Verify all registered tools satisfy the tool admission policy."""
    section("computer tool audit")

    if not REGISTRY_PATH.exists():
        warn("registry.py not found — cannot audit tools.")
        return

    text = REGISTRY_PATH.read_text()
    tools = _parse_tools(text)

    if not tools:
        warn("No ToolDescriptor entries found in registry.py")
        warn("This may indicate registry.py uses a different format.")
        print()
        # Fallback: count and report
        tool_count = text.count("ToolDescriptor(")
        kv("Tool definitions found", tool_count)
        print()
        if tool_count > 0:
            ok("Registry appears populated — update tool audit parser for new format.")
        return

    print(f"  Found {len(tools)} tool(s)\n")
    all_pass = True
    rows = []
    for tool in tools:
        ok_flag, failures = _check_admission(tool)
        if not ok_flag:
            all_pass = False
        rows.append([
            tool["name"][:30],
            tool.get("primary_mode") or "—",
            tool.get("trust_tier") or "—",
            "✓" if ok_flag else "✗",
            "; ".join(failures)[:40] if failures else "",
        ])
    table(["tool_name", "mode", "tier", "", "admission_issues"], rows, col_width=22)

    print()
    if all_pass:
        ok("All tools satisfy the admission policy.")
    else:
        violations = sum(1 for t in tools if not _check_admission(t)[0])
        warn(f"{violations} tool(s) violate admission policy — see tool-admission-policy.md.")
    print()


@cmd.command("prune")
def tool_prune() -> None:
    """List tools eligible for deprecation per tool-lifecycle-policy.md (dry-run)."""
    section("computer tool prune")

    if not REGISTRY_PATH.exists():
        warn("registry.py not found.")
        return

    text = REGISTRY_PATH.read_text()
    tools = _parse_tools(text)

    # Prune candidates: missing eval_fixture or audit_payload (policy violation → deprecation eligible)
    candidates = []
    for t in tools:
        reasons = []
        if not t.get("eval_fixture"):
            reasons.append("no eval fixture")
        if not t.get("audit_payload"):
            reasons.append("no audit payload")
        if not t.get("primary_mode"):
            reasons.append("no primary mode")
        if reasons:
            candidates.append((t["name"], "; ".join(reasons)))

    if not candidates:
        ok("No tools eligible for deprecation at this time.")
        print()
        return

    print(f"  {len(candidates)} tool(s) eligible for deprecation (dry-run):\n")
    for name, reason in candidates:
        print(f"  → {name:<35} {reason}")
    print()
    print("  To deprecate: set deprecated_at in registry entry and bump version.")
    print("  See docs/architecture/tool-lifecycle-policy.md.\n")
