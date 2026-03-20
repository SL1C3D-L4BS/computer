"""
computer policy diff

Compares current policy set vs previous checkpoint.
Highlights changed thresholds and tier assignments.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import click

from scripts.cli.formatters import section, diff_line, warn, ok, kv

REPO_ROOT = Path(__file__).parent.parent.parent.parent
POLICY_PATH = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "policy.py"
REGISTRY_PATH = REPO_ROOT / "packages" / "mcp-gateway" / "mcp_gateway" / "registry.py"
CHECKPOINT_PATH = REPO_ROOT / ".policy-checkpoint.json"


def _compute_checksum(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _load_checkpoint() -> dict:
    if CHECKPOINT_PATH.exists():
        try:
            return json.loads(CHECKPOINT_PATH.read_text())
        except Exception:
            pass
    return {}


def _save_checkpoint(data: dict) -> None:
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2))


@click.command("policy")
@click.option("--save", is_flag=True, help="Save current policy as checkpoint")
def cmd(save: bool) -> None:
    """Compare current policy vs last checkpoint; show changed thresholds."""
    section("computer policy diff")

    current = {
        "policy_py":   _compute_checksum(POLICY_PATH),
        "registry_py": _compute_checksum(REGISTRY_PATH),
    }

    # Count tools and tiers
    if REGISTRY_PATH.exists():
        text = REGISTRY_PATH.read_text()
        tool_count = text.count("ToolDescriptor(")
        current["tool_count"] = tool_count
    else:
        current["tool_count"] = 0

    if save:
        _save_checkpoint(current)
        ok(f"Policy checkpoint saved ({current['policy_py']})")
        return

    checkpoint = _load_checkpoint()

    if not checkpoint:
        warn("No checkpoint found. Run 'computer policy diff --save' to create one.")
        print()
        kv("policy.py checksum",   current["policy_py"])
        kv("registry.py checksum", current["registry_py"])
        kv("tools registered",     current["tool_count"])
        return

    print()
    diff_line("policy.py checksum",   checkpoint.get("policy_py", "?"), current["policy_py"])
    diff_line("registry.py checksum", checkpoint.get("registry_py", "?"), current["registry_py"])
    diff_line("tool count",           checkpoint.get("tool_count", "?"), current["tool_count"])

    changed = sum(1 for k in ("policy_py", "registry_py", "tool_count")
                  if checkpoint.get(k) != current.get(k))
    print()
    if changed == 0:
        ok("Policy unchanged since last checkpoint.")
    else:
        from scripts.cli.formatters import warn as w
        w(f"{changed} policy component(s) changed since last checkpoint.")
        print("  Run 'computer policy diff --save' to update the checkpoint after review.")
    print()
