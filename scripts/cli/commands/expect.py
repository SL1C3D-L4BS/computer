"""
computer expectation capture

Interactive prompt that records an ExpectationDelta when the user
overrides/corrects/says "not now". Feeds into eval fixtures and
reflection proposals.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click

from scripts.cli.formatters import section, ok, warn, kv

REPO_ROOT = Path(__file__).parent.parent.parent.parent
EXPECTATION_STORE = REPO_ROOT / "packages" / "eval-fixtures" / "eval_fixtures" / "expectation_deltas.jsonl"


CORRECTION_TYPES = ["override", "stop", "not_now", "correction", "redirect"]


@click.command("expect")
@click.option("--trace-id", default=None, help="Trace ID of the decision being corrected")
@click.option("--user-id", default="founder", help="User making the correction")
@click.option("--non-interactive", is_flag=True, hidden=True,
              help="Skip prompts (for testing)")
def cmd(trace_id: str | None, user_id: str, non_interactive: bool) -> None:
    """Interactive capture of ExpectationDelta: record corrections for eval fixtures."""
    section("computer expectation capture")
    print("  Record a human correction to feed into eval fixtures and reflection.\n")

    if non_interactive:
        # Testing stub
        delta = {
            "trace_id": trace_id or "test-trace",
            "user_id": user_id,
            "user_intent": "test intent",
            "system_decision": "INTERRUPT",
            "correction": "not now",
            "correction_type": "not_now",
            "context": {},
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "id": str(uuid.uuid4()),
        }
        _write_delta(delta)
        ok(f"ExpectationDelta saved (non-interactive stub)")
        return

    if trace_id is None:
        trace_id = click.prompt("  Trace ID (from 'computer trace')", default="unknown")
    kv("trace_id", trace_id)

    user_intent = click.prompt("  What did you expect the system to do?")
    system_decision = click.prompt("  What did the system actually do?")
    correction = click.prompt("  What did you say/do instead? (correction/action)")

    print(f"\n  Correction types: {', '.join(CORRECTION_TYPES)}")
    correction_type = click.prompt("  Type", type=click.Choice(CORRECTION_TYPES), default="correction")

    context_str = click.prompt("  Any extra context? (JSON or blank)", default="")
    try:
        context = json.loads(context_str) if context_str.strip() else {}
    except json.JSONDecodeError:
        context = {"raw": context_str}

    delta = {
        "id": str(uuid.uuid4()),
        "trace_id": trace_id,
        "user_id": user_id,
        "user_intent": user_intent,
        "system_decision": system_decision,
        "correction": correction,
        "correction_type": correction_type,
        "context": context,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }

    _write_delta(delta)
    print()
    ok(f"ExpectationDelta saved → {EXPECTATION_STORE.name}")
    print(f"  ID: {delta['id']}")
    print(f"  The reflection engine will include this in the next CandidatePolicyAdjustment cycle.\n")


def _write_delta(delta: dict) -> None:
    EXPECTATION_STORE.parent.mkdir(parents=True, exist_ok=True)
    with EXPECTATION_STORE.open("a") as f:
        f.write(json.dumps(delta) + "\n")
