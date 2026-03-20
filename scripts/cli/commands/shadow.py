"""
computer shadow review

Lists divergence log from eval-runner /eval/shadow.
Shows live vs shadow policy disagreements.
"""
from __future__ import annotations

import json

import click

from scripts.cli.formatters import section, table, kv, warn, ok

EVAL_RUNNER_URL = "http://localhost:8700"


def _get_divergences(limit: int = 20, div_type: str | None = None) -> tuple[bool, list]:
    import urllib.request
    url = EVAL_RUNNER_URL + f"/eval/shadow/divergences?limit={limit}"
    if div_type:
        url += f"&type={div_type}"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())
            return True, data.get("divergences", [])
    except Exception as e:
        return False, []


def _stub_divergences() -> list[dict]:
    return [
        {"trace_id": "trace-abc123", "type": "attention", "live": "INTERRUPT", "shadow": "DIGEST",
         "timestamp": "2026-03-18T14:22:00Z", "confidence_delta": 0.08},
        {"trace_id": "trace-def456", "type": "routing", "live": "voice-gateway",
         "shadow": "ops-web", "timestamp": "2026-03-18T11:05:00Z", "confidence_delta": 0.15},
        {"trace_id": "trace-ghi789", "type": "tool_selection", "live": "site.read_snapshot",
         "shadow": "greenhouse.explain_drift", "timestamp": "2026-03-17T09:31:00Z",
         "confidence_delta": 0.23},
    ]


@click.command("shadow")
@click.option("--limit", default=20, help="Max divergences to show")
@click.option("--type", "div_type", default=None,
              help="Filter type: attention|routing|tool_selection")
def cmd(limit: int, div_type: str | None) -> None:
    """Show live vs shadow policy divergences from eval-runner."""
    section("computer shadow review")

    success, divergences = _get_divergences(limit, div_type)
    if not success:
        warn("eval-runner unreachable — showing stub divergence data.\n")
        divergences = _stub_divergences()

    if not divergences:
        ok("No divergences found in shadow evaluation queue.")
        return

    print(f"  Found {len(divergences)} divergence(s):\n")
    rows = []
    for d in divergences:
        rows.append([
            d.get("trace_id", "?")[:16],
            d.get("type", "?"),
            str(d.get("live", "?"))[:20],
            str(d.get("shadow", "?"))[:20],
            f"{d.get('confidence_delta', 0.0):.2f}",
        ])
    table(["trace_id", "type", "live_decision", "shadow_decision", "conf_delta"],
          rows, col_width=22)

    high = [d for d in divergences if d.get("confidence_delta", 0) > 0.20]
    if high:
        print(f"\n  [!] {len(high)} high-confidence divergence(s) — review before next policy publish.")

    print()
    print("  To freeze baseline: computer shadow baseline-freeze")
    print("  To run replay:      computer replay <trace_id>\n")
