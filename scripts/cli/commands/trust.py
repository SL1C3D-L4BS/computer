"""
computer trust report [--period 7d]

Aggregates all 11 trust KPIs by mode/domain for the given window.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

import click

from scripts.cli.formatters import section, table, kv, warn, ok

REPO_ROOT = Path(__file__).parent.parent.parent.parent
AUDIT_LOG = REPO_ROOT / "services" / "runtime-kernel" / "audit_log.jsonl"

KPIS = [
    "suggestion_acceptance_rate",
    "interrupt_dismissal_rate",
    "correction_rate",
    "approval_latency_p50",
    "approval_latency_p95",
    "override_rate",
    "loop_closure_rate",
    "privacy_incident_count",
    "clarification_rate",
    "regret_rate",
    "spoken_regret_rate",
    "decision_load_index",
]


def _parse_period(period: str) -> int:
    """Return period in days."""
    period = period.strip().lower()
    if period.endswith("d"):
        return int(period[:-1])
    if period.endswith("w"):
        return int(period[:-1]) * 7
    return 7


def _load_kpis_from_log(since: datetime) -> dict[str, list]:
    """Scan audit log for KPI signals in the period."""
    signals: dict[str, list] = {kpi: [] for kpi in KPIS}
    if not AUDIT_LOG.exists():
        return signals

    for line in AUDIT_LOG.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            ts_str = rec.get("timestamp", rec.get("ts", ""))
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts < since:
                    continue
            obs_type = rec.get("observation_type", "")
            if obs_type == "dismissal":
                signals["interrupt_dismissal_rate"].append(1)
            elif obs_type == "acknowledgment":
                signals["interrupt_dismissal_rate"].append(0)
            elif obs_type in ("regret", "stop", "not_now"):
                signals["regret_rate"].append(1)
                if rec.get("surface") in ("VOICE", "voice"):
                    signals["spoken_regret_rate"].append(1)
            elif obs_type == "clarification":
                signals["clarification_rate"].append(1)
            elif obs_type == "override":
                signals["override_rate"].append(1)
            elif obs_type == "loop_closed":
                signals["loop_closure_rate"].append(1)
            elif obs_type == "privacy_violation":
                signals["privacy_incident_count"].append(1)
        except (json.JSONDecodeError, ValueError):
            continue
    return signals


def _stub_kpis() -> dict[str, float]:
    return {
        "suggestion_acceptance_rate": 0.74,
        "interrupt_dismissal_rate":   0.18,
        "correction_rate":            0.09,
        "approval_latency_p50":       3.2,
        "approval_latency_p95":       18.7,
        "override_rate":              0.06,
        "loop_closure_rate":          0.81,
        "privacy_incident_count":     0.0,
        "clarification_rate":         0.11,
        "regret_rate":                0.04,
        "spoken_regret_rate":         0.02,
        "decision_load_index":        1.4,
    }


THRESHOLDS = {
    "suggestion_acceptance_rate": (">=", 0.65),
    "interrupt_dismissal_rate":   ("<=", 0.30),
    "correction_rate":            ("<=", 0.20),
    "override_rate":              ("<=", 0.15),
    "loop_closure_rate":          (">=", 0.70),
    "privacy_incident_count":     ("==", 0.0),
    "clarification_rate":         ("<=", 0.20),
    "regret_rate":                ("<=", 0.10),
    "spoken_regret_rate":         ("<=", 0.05),
    "decision_load_index":        ("<=", 3.0),
}


def _passes(kpi: str, value: float) -> bool:
    if kpi not in THRESHOLDS:
        return True
    op, threshold = THRESHOLDS[kpi]
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == "==":
        return value == threshold
    return True


@click.command("trust")
@click.option("--period", default="7d", help="Reporting window (e.g. 7d, 30d)")
def cmd(period: str) -> None:
    """Trust KPI report across all 11 metrics for the given period."""
    section(f"computer trust report  --period {period}")

    days = _parse_period(period)
    since = datetime.now(timezone.utc) - timedelta(days=days)

    live_signals = _load_kpis_from_log(since)
    has_live = any(v for v in live_signals.values())

    if has_live:
        # Compute rates from raw signal counts
        kpis: dict[str, float] = {}
        for kpi in KPIS:
            vals = live_signals[kpi]
            if vals:
                kpis[kpi] = sum(vals) / len(vals)
            else:
                kpis[kpi] = 0.0
    else:
        warn("No live audit signals in period — showing stub data.\n")
        kpis = _stub_kpis()

    rows = []
    passed = 0
    for kpi in KPIS:
        value = kpis.get(kpi, 0.0)
        ok_flag = _passes(kpi, value)
        if ok_flag:
            passed += 1
        threshold_info = ""
        if kpi in THRESHOLDS:
            op, t = THRESHOLDS[kpi]
            threshold_info = f"{op}{t}"
        rows.append([kpi, f"{value:.3f}", threshold_info, "✓" if ok_flag else "✗"])

    table(["KPI", "value", "threshold", ""], rows, col_width=30)
    print()
    if passed == len(KPIS):
        ok(f"All {len(KPIS)} KPIs within threshold for the past {period}.")
    else:
        warn(f"{len(KPIS) - passed} KPI(s) outside threshold. Review drift-remediation-policy.md.")
    print()
