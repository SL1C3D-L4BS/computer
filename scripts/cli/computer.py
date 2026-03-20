#!/usr/bin/env python3
"""
computer — V4 Operator CLI

Usage: computer <command> [options]

Core 8 (operator surface):
  doctor [--fix]            Service health, version drift, MCP registry, trace pipeline
  trace <trace_id>          Full CRK execution chain for a trace
  explain <trace_id>        Human-readable decision explanation
  replay <trace_id>         Re-run trace through current policy; diff vs original
  simulate [scenario]       Run assistant scenario, PASS/FAIL per step
  workflow [list|inspect|resume|cancel|sweep]  Durable workflow operations
  auth <subject> <action> <resource>           Dry-run auth check
  memory [--gc]             Memory scope audit and GC recommendations

Extended 13 (trust + policy + human alignment):
  founder brief             Daily founder briefing with decision load
  founder load              decision_load_index = open × age / resolved_per_day
  policy [--save]           Policy diff vs checkpoint
  trust [--period 7d]       11 trust KPI report
  shadow                    Shadow mode divergence review
  tool audit                Verify tools satisfy admission policy
  tool prune                List tools eligible for deprecation
  drift [--period 7d]       Weekly drift digest
  summarize <trace_id>      1-line decision summary
  expect                    Interactive ExpectationDelta capture
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow imports from repo root when run directly
_repo_root = Path(__file__).parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

import click

from scripts.cli.commands.doctor import cmd as doctor_cmd
from scripts.cli.commands.trace import (
    trace_cmd, explain_cmd, replay_cmd, summarize_cmd
)
from scripts.cli.commands.simulate import cmd as simulate_cmd
from scripts.cli.commands.workflow import cmd as workflow_cmd
from scripts.cli.commands.auth import cmd as auth_cmd
from scripts.cli.commands.memory import cmd as memory_cmd
from scripts.cli.commands.founder import cmd as founder_cmd
from scripts.cli.commands.policy import cmd as policy_cmd
from scripts.cli.commands.trust import cmd as trust_cmd
from scripts.cli.commands.shadow import cmd as shadow_cmd
from scripts.cli.commands.tools import cmd as tools_cmd
from scripts.cli.commands.drift import cmd as drift_cmd
from scripts.cli.commands.expect import cmd as expect_cmd


@click.group()
@click.version_option("4.0.0", prog_name="computer")
def cli() -> None:
    """Computer V4 — Operator CLI for the Cyber-Physical Intelligence System."""


# ── Core 8 ────────────────────────────────────────────────────────────────
cli.add_command(doctor_cmd,   name="doctor")
cli.add_command(trace_cmd,    name="trace")
cli.add_command(explain_cmd,  name="explain")
cli.add_command(replay_cmd,   name="replay")
cli.add_command(simulate_cmd, name="simulate")
cli.add_command(workflow_cmd, name="workflow")
cli.add_command(auth_cmd,     name="auth")
cli.add_command(memory_cmd,   name="memory")

# ── Extended 13 ───────────────────────────────────────────────────────────
cli.add_command(founder_cmd,  name="founder")
cli.add_command(policy_cmd,   name="policy")
cli.add_command(trust_cmd,    name="trust")
cli.add_command(shadow_cmd,   name="shadow")
cli.add_command(tools_cmd,    name="tool")
cli.add_command(drift_cmd,    name="drift")
cli.add_command(summarize_cmd, name="summarize")
cli.add_command(expect_cmd,   name="expect")


if __name__ == "__main__":
    cli()
