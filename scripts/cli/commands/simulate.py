"""
computer simulate <scenario>

Runs a social/assistant scenario from tests/scenarios/assistant/
and prints structured PASS/FAIL per step.
"""
from __future__ import annotations

import json
from pathlib import Path

import click

from scripts.cli.formatters import section, status_line, warn, summary_line

REPO_ROOT = Path(__file__).parent.parent.parent.parent
SCENARIOS_DIR = REPO_ROOT / "tests" / "scenarios" / "assistant"


def _list_scenarios() -> list[str]:
    if not SCENARIOS_DIR.exists():
        return []
    return [f.stem for f in sorted(SCENARIOS_DIR.glob("*.json"))]


def _run_scenario(scenario_id: str) -> tuple[int, int]:
    """Load and 'run' a scenario file. Returns (passed, total)."""
    path = SCENARIOS_DIR / f"{scenario_id}.json"
    if not path.exists():
        # Try prefix match
        matches = list(SCENARIOS_DIR.glob(f"*{scenario_id}*.json"))
        if not matches:
            return 0, 0
        path = matches[0]

    data = json.loads(path.read_text())
    steps = data.get("steps", [])
    passed = 0
    for i, step in enumerate(steps, 1):
        actor = step.get("actor", "?")
        utterance = step.get("utterance", "")[:60]
        expected_mode = step.get("expected_mode")
        expected_decision = step.get("expected_decision")

        # Stub evaluation: structural check only (no live service call)
        ok = bool(actor) and bool(utterance)
        notes = []
        if expected_mode:
            notes.append(f"mode={expected_mode}")
        if expected_decision:
            notes.append(f"decision={expected_decision}")
        detail = " | ".join(notes) if notes else ""
        status_line(f"step {i:02d}  {actor}: {utterance[:40]}", ok, detail if not ok else "")
        if ok:
            passed += 1

    return passed, len(steps)


@click.command("simulate")
@click.argument("scenario", required=False, default=None)
@click.option("--list", "list_only", is_flag=True, help="List available scenarios")
def cmd(scenario: str | None, list_only: bool) -> None:
    """Run an assistant scenario from tests/scenarios/assistant/."""
    available = _list_scenarios()

    if list_only or scenario is None:
        section("computer simulate — available scenarios")
        if not available:
            warn("No scenario files found in tests/scenarios/assistant/")
        for name in available:
            print(f"  • {name}")
        print()
        if scenario is None and not list_only:
            warn("Pass a scenario name or --list")
        return

    section(f"computer simulate  {scenario}")

    if not available:
        warn("No scenario files found. Run from repo root.")
        return

    passed, total = _run_scenario(scenario)
    if total == 0:
        warn(f"Scenario '{scenario}' not found.")
        print(f"  Available: {', '.join(available)}\n")
        return

    summary_line(passed, total, "scenario steps")
