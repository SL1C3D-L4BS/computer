"""
computer drift digest [--period 7d]

Summarizes all drift events, overrides used, unresolved anomalies,
and recommended actions for the period. Designed for weekly ritual review.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from scripts.cli.formatters import section, table, kv, warn, ok, err

REPO_ROOT = Path(__file__).parent.parent.parent.parent
AUDIT_LOG = REPO_ROOT / "services" / "runtime-kernel" / "audit_log.jsonl"

MONITORS = [
    ("confidence_miscalibration", "Brier score > 0.25",          "AI eval lead",          48),
    ("attention_fatigue",         "Dismissal rate > 0.30",        "Attention-engine owner", 24),
    ("memory_growth",             "Loop count > 5%/day",          "Memory-service owner",   72),
    ("auth_denial_spike",         "> 3x baseline in 24h",         "Security/identity owner", 12),
]


def _parse_period(period: str) -> int:
    period = period.strip().lower()
    if period.endswith("d"):
        return int(period[:-1])
    if period.endswith("w"):
        return int(period[:-1]) * 7
    return 7


def _load_drift_events(since: datetime) -> list[dict]:
    events = []
    if not AUDIT_LOG.exists():
        return events
    for line in AUDIT_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("event_type") not in ("drift_alarm", "drift_override", "drift_resolved"):
                continue
            ts_str = rec.get("timestamp", "")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < since:
                    continue
            events.append(rec)
        except (json.JSONDecodeError, ValueError):
            continue
    return events


def _stub_digest(days: int) -> dict:
    return {
        "alarms_fired": 2,
        "overrides_used": 1,
        "unresolved": 1,
        "events": [
            {"type": "drift_alarm",    "monitor": "attention_fatigue",
             "detail": "dismissal_rate=0.33 at 2026-03-15 09:00Z",
             "resolved": True, "override_used": True},
            {"type": "drift_alarm",    "monitor": "confidence_miscalibration",
             "detail": "Brier=0.27 in WORK domain",
             "resolved": False, "override_used": False},
        ],
        "recommendations": [
            "Review confidence_miscalibration: Brier > 0.25 unresolved for 48h",
            "Schedule weekly drift ritual (suggest Monday morning)",
        ],
    }


@click.command("drift")
@click.option("--period", default="7d", help="Reporting window (e.g. 7d, 14d)")
def cmd(period: str) -> None:
    """Weekly drift digest: alarms, overrides, unresolved anomalies, recommendations."""
    section(f"computer drift digest  --period {period}")

    days = _parse_period(period)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    live_events = _load_drift_events(since)

    if live_events:
        alarms   = [e for e in live_events if e.get("event_type") == "drift_alarm"]
        overrides = [e for e in live_events if e.get("event_type") == "drift_override"]
        resolved  = [e for e in live_events if e.get("event_type") == "drift_resolved"]
        unresolved_monitors = set(e.get("monitor") for e in alarms) - set(e.get("monitor") for e in resolved)
        print(f"\n  Period: last {days} days")
        kv("Alarms fired",     len(alarms))
        kv("Overrides used",   len(overrides))
        kv("Resolved",         len(resolved))
        kv("Unresolved",       len(unresolved_monitors))
    else:
        warn("No live drift events in audit log — showing stub data.\n")
        data = _stub_digest(days)
        kv("Alarms fired",   data["alarms_fired"])
        kv("Overrides used", data["overrides_used"])
        kv("Unresolved",     data["unresolved"])

        print("\n  EVENTS")
        for ev in data["events"]:
            status = "✓ resolved" if ev["resolved"] else "✗ OPEN"
            override = " [override used]" if ev["override_used"] else ""
            print(f"  [{status}{override}] {ev['monitor']}: {ev['detail']}")

        print("\n  RECOMMENDATIONS")
        for rec in data["recommendations"]:
            print(f"  → {rec}")

    print("\n  DRIFT MONITOR STATUS")
    rows = []
    for monitor, threshold, owner, cooldown_h in MONITORS:
        rows.append([monitor, threshold, owner, f"{cooldown_h}h"])
    table(["monitor", "threshold", "owner", "cooldown"], rows, col_width=26)

    print()
    print("  Run weekly: computer drift digest --period 7d")
    print("  See docs/safety/drift-remediation-policy.md for remediation paths.\n")
