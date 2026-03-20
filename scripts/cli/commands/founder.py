"""
computer founder brief
computer founder load

Founder mode surfaces: daily briefing and cognitive load index.
"""
from __future__ import annotations

import json
from datetime import date

import click

from scripts.cli.formatters import section, kv, warn, ok, err, table

MCP_GATEWAY_URL = "http://localhost:8500"
RUNTIME_KERNEL_URL = "http://localhost:8100"


def _invoke_tool(tool_name: str, arguments: dict = {}) -> tuple[bool, dict]:
    import urllib.request
    payload = {
        "tool_name": tool_name,
        "arguments": arguments,
        "execution_context": {
            "mode": "WORK",
            "surface": "OPS",
            "user_id": "founder",
            "request_id": "cli-brief",
            "trace_id": "cli-brief",
            "intent_class": "founder_briefing",
            "risk_class": "LOW",
            "origin": "OPERATOR",
        },
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        MCP_GATEWAY_URL + "/tools/invoke",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return True, json.loads(resp.read())
    except Exception as e:
        return False, {"error": str(e)}


@click.group("founder")
def cmd() -> None:
    """Founder mode operator surfaces."""


@cmd.command("brief")
def brief() -> None:
    """Daily founder briefing: ranked decision agenda."""
    section(f"computer founder brief  {date.today().isoformat()}")

    success, data = _invoke_tool("briefing.daily")
    if not success:
        warn(f"mcp-gateway unreachable: {data.get('error')}")
        _stub_brief()
        return

    result = data.get("structuredContent", data)
    load = result.get("decision_load", {})
    kv("Decision load",  f"T1={load.get('t1_count',0)}  T2={load.get('t2_count',0)}  total={load.get('total',0)}")
    kv("Overloaded",     load.get("overloaded", False))
    metrics = result.get("metrics", {})
    kv("Open loops",     metrics.get("open_loops", "?"))
    kv("Burn-down rate", f"{metrics.get('backlog_burn_down_rate', 0):.2f}")
    kv("Mean decision age", f"{metrics.get('mean_decision_age_hours', 0):.1f}h")

    action_items = result.get("action_required", [])
    if action_items:
        print(f"\n  ACTION REQUIRED ({len(action_items)} items)")
        for item in action_items:
            urgency = item.get("urgency", 0)
            print(f"  [{urgency:.0%}] {item.get('description', '?')[:70]}")

    print()


def _stub_brief() -> None:
    print("  [stub] Founder briefing unavailable — showing example structure.\n")
    print("  T1 Action items:")
    print("    [85%] Review authentication migration ADR-033 before Thursday")
    print("    [70%] Approve V4 workflow registry schema")
    print("\n  T2 Stale loops (need closure decision):")
    print("    Loop: greenhouse-sensor-calibration  (freshness=0.18, age=42h)")
    print("\n  Metrics:")
    kv("  Open loops",      12)
    kv("  Pending commits.", 3)
    kv("  Burn-down rate",  "0.74/day")
    print()


@cmd.command("load")
def load() -> None:
    """Print decision_load_index: open_decisions × avg_age / resolved_per_day."""
    section("computer founder load")

    success, data = _invoke_tool("loops.open_for_founder")
    if not success:
        warn(f"mcp-gateway unreachable: {data.get('error')}")
        _stub_load()
        return

    result = data.get("structuredContent", data)
    total_active = result.get("total_active", 0)
    burn_rate = result.get("burn_down_rate", 0.0)

    # decision_load_index = open_decisions × avg_decision_age / decisions_resolved_per_day
    # Approximated from available fields
    avg_age_est = 24.0  # hours; would come from loops data in production
    resolved_per_day = max(burn_rate, 0.01)
    index = (total_active * avg_age_est) / (resolved_per_day * 24)

    kv("Active open loops",      total_active)
    kv("Burn-down rate",         f"{burn_rate:.2f}/day")
    kv("Abandonment candidates", result.get("abandonment_candidates", "?"))
    print()
    print(f"  decision_load_index = {index:.2f}")
    print()
    if index < 1.0:
        ok("Load is healthy — founder mode is burning down faster than accumulating.")
    elif index < 3.0:
        warn("Load is elevated — review T2 stale loops this session.")
    else:
        err("Load is high — founder mode is accumulating debt. Prioritize abandonment decisions.")
    print()


def _stub_load() -> None:
    print("  [stub] Showing example decision_load_index calculation.\n")
    print("  open_decisions=12  avg_age=18h  resolved_per_day=4.2")
    print()
    index = (12 * 18) / (4.2 * 24)
    print(f"  decision_load_index = {index:.2f}  (healthy < 1.0)")
    print()
