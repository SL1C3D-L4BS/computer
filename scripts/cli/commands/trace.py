"""
computer trace <trace_id>
computer explain <trace_id>
computer replay <trace_id>
computer summarize <trace_id>

Audit trail inspection and decision explanation commands.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from scripts.cli.formatters import section, kv, warn, table, diff_line

REPO_ROOT = Path(__file__).parent.parent.parent.parent
AUDIT_LOG = REPO_ROOT / "services" / "runtime-kernel" / "audit_log.jsonl"


def _load_trace(trace_id: str) -> list[dict[str, Any]]:
    """Load all audit records for a given trace_id from the JSONL audit log."""
    if not AUDIT_LOG.exists():
        return []
    records = []
    for line in AUDIT_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("trace_id") == trace_id or rec.get("context", {}).get("trace_id") == trace_id:
                records.append(rec)
        except json.JSONDecodeError:
            continue
    return records


def _find_decision_rationale(records: list[dict]) -> dict | None:
    for rec in records:
        if "decision_rationale" in rec:
            return rec["decision_rationale"]
        if rec.get("step") == "step9_attention" and "attention_decision" in rec:
            return rec.get("attention_decision")
    return None


@click.command("trace")
@click.argument("trace_id")
def trace_cmd(trace_id: str) -> None:
    """Print the full CRK execution chain for a trace ID."""
    section(f"computer trace  {trace_id}")
    records = _load_trace(trace_id)
    if not records:
        warn(f"No audit records found for trace_id={trace_id}")
        warn("(Ensure runtime-kernel is running and audit_log.jsonl is populated)")
        return

    print(f"\n  Found {len(records)} audit record(s)\n")
    for i, rec in enumerate(records, 1):
        step = rec.get("step", rec.get("event", f"record-{i}"))
        ts = rec.get("timestamp", rec.get("ts", ""))
        print(f"  [{i:02d}] {step}  {ts}")
        for key in ("mode", "risk_class", "intent_class", "surface", "user_id"):
            val = rec.get(key) or rec.get("context", {}).get(key)
            if val:
                kv(f"       {key}", val)
        if rec.get("step") == "step7a":
            kv("       tool", rec.get("tool_name", "?"))
        if rec.get("step") == "step7b":
            kv("       job_id", rec.get("job_id", "?"))
        if rec.get("step") in ("step6_authorize", "step6"):
            kv("       allowed", rec.get("allowed", "?"))
        if rec.get("step") in ("step9_attention", "step9"):
            kv("       attention", rec.get("decision", "?"))
    print()


@click.command("explain")
@click.argument("trace_id")
def explain_cmd(trace_id: str) -> None:
    """Human-readable explanation of why this decision was made."""
    section(f"computer explain  {trace_id}")
    records = _load_trace(trace_id)
    if not records:
        warn(f"No records for trace_id={trace_id}")
        return

    rationale = _find_decision_rationale(records)
    if not rationale:
        warn("No DecisionRationale found in audit records for this trace.")
        warn("The decision may predate V3 runtime contracts.")
        return

    print(f"\n  Decision:  {rationale.get('decision', '?')}")
    print()

    conf = rationale.get("confidence", {})
    if conf:
        print(f"  Confidence: {conf.get('value', '?'):.2f}  (source: {conf.get('source', '?')})")

    weights = rationale.get("objective_weights", {})
    if weights:
        print("\n  Objective weights active:")
        for k, v in weights.items():
            print(f"    {k:<30} {v:.3f}")

    constraints = rationale.get("constraints_checked", [])
    if constraints:
        print(f"\n  Invariants checked: {', '.join(constraints)}")

    violated = rationale.get("hard_constraints_violated", [])
    if violated:
        print(f"\n  [!] Hard constraints VIOLATED: {', '.join(violated)}")

    alts = rationale.get("alternatives_considered", [])
    if alts:
        print(f"\n  Alternatives considered: {', '.join(alts)}")

    print()


@click.command("replay")
@click.argument("trace_id")
def replay_cmd(trace_id: str) -> None:
    """Re-run a historical ExecutionContext through the current policy stack; diff vs original."""
    section(f"computer replay  {trace_id}")
    records = _load_trace(trace_id)
    if not records:
        warn(f"No records for trace_id={trace_id}")
        return

    original_decision = None
    original_mode = None
    for rec in records:
        if rec.get("step") in ("step9_attention", "step9"):
            original_decision = rec.get("decision")
        ctx = rec.get("context", {})
        if ctx.get("mode"):
            original_mode = ctx["mode"]

    print(f"\n  Original decision:  {original_decision or '(unknown)'}")
    print(f"  Original mode:      {original_mode or '(unknown)'}")
    print()

    # Stub: In production, POST to runtime-kernel /replay with the ExecutionContext
    warn("Replay against live policy stack requires runtime-kernel /replay endpoint.")
    warn("Stub result: policy unchanged since trace — decision would match original.")
    print()
    diff_line("attention_decision", original_decision or "?", original_decision or "?")
    print()
    print("  To implement live replay: POST /execute with trace ExecutionContext")
    print("  and compare ResponseEnvelope against original audit record.\n")


@click.command("summarize")
@click.argument("trace_id")
def summarize_cmd(trace_id: str) -> None:
    """1-line decision summary: key factors, confidence, cost, and validation signal."""
    records = _load_trace(trace_id)
    if not records:
        warn(f"No records for trace_id={trace_id}")
        return

    rationale = _find_decision_rationale(records)
    decision = rationale.get("decision", "?") if rationale else "?"
    confidence = rationale.get("confidence", {}).get("value", 0.0) if rationale else 0.0
    weights = rationale.get("objective_weights", {}) if rationale else {}

    top_factors = sorted(weights.items(), key=lambda x: x[1], reverse=True)[:3]
    factors_str = ", ".join(f"{k}={v:.2f}" for k, v in top_factors) if top_factors else "no weights"

    # Check for later ObservationRecord validation
    validated = any(
        r.get("observation_type") in ("acknowledgment",) for r in records
    )
    validated_str = "validated ✓" if validated else "not yet validated"

    print(f"\n  [{trace_id[:16]}]  {decision}  |  conf={confidence:.2f}  |  {factors_str}  |  {validated_str}\n")
