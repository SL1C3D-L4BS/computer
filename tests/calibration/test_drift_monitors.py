"""
Drift Monitor Calibration Tests — V4

Tests that drift monitor thresholds, ownership, and override rules
are correctly defined and internally consistent.

These are structural/contract tests: they verify the model is sane,
not that live KPIs are within bounds (that's the responsibility of
the runtime monitoring system and the weekly drift digest ritual).

Reference: docs/architecture/trust-kpis-and-drift-model.md
           docs/safety/drift-remediation-policy.md
"""
from __future__ import annotations

import pytest


# ── Monitor Definitions ────────────────────────────────────────────────────────

DRIFT_MONITORS = [
    {
        "name": "confidence_miscalibration",
        "threshold": 0.25,
        "threshold_direction": "above",
        "metric": "brier_score",
        "owner": "AI eval lead",
        "override_cooldown_hours": 48,
        "auto_ticket": True,
        "auto_reversion_threshold": 0.35,
        "auto_reversion_action": "conservative_confidence",
    },
    {
        "name": "attention_fatigue",
        "threshold": 0.30,
        "threshold_direction": "above",
        "metric": "interrupt_dismissal_rate",
        "owner": "Attention-engine owner",
        "override_cooldown_hours": 24,
        "auto_ticket": True,
        "auto_reversion_threshold": 0.50,
        "auto_reversion_action": "digest_only_mode",
    },
    {
        "name": "memory_growth",
        "threshold": 0.05,
        "threshold_direction": "above",
        "metric": "loop_count_daily_growth_rate",
        "owner": "Memory-service owner",
        "override_cooldown_hours": 72,
        "auto_ticket": True,
        "auto_reversion_threshold": None,  # I-09 invariant handles this
        "auto_reversion_action": "archive_low_freshness",
    },
    {
        "name": "auth_denial_spike",
        "threshold": 3.0,
        "threshold_direction": "above",
        "metric": "auth_denial_rate_vs_baseline",
        "owner": "Security/identity owner",
        "override_cooldown_hours": 12,
        "auto_ticket": True,
        "auto_reversion_threshold": None,  # Auth is always enforced; no auto-reversion
        "auto_reversion_action": None,
    },
]

TRUST_KPIS = [
    {"name": "suggestion_acceptance_rate",    "threshold": 0.65, "op": ">="},
    {"name": "interrupt_dismissal_rate",      "threshold": 0.30, "op": "<="},
    {"name": "correction_rate",               "threshold": 0.20, "op": "<="},
    {"name": "override_rate",                 "threshold": 0.15, "op": "<="},
    {"name": "loop_closure_rate",             "threshold": 0.70, "op": ">="},
    {"name": "privacy_incident_count",        "threshold": 0.0,  "op": "=="},
    {"name": "clarification_rate",            "threshold": 0.20, "op": "<="},
    {"name": "regret_rate",                   "threshold": 0.10, "op": "<="},
    {"name": "spoken_regret_rate",            "threshold": 0.05, "op": "<="},
    {"name": "decision_load_index",           "threshold": 3.0,  "op": "<="},
    {"name": "approval_latency_p50",          "threshold": None, "op": "track"},
    {"name": "approval_latency_p95",          "threshold": None, "op": "track"},
]


class TestDriftMonitorDefinitions:
    def test_all_monitors_have_required_fields(self):
        required = {"name", "threshold", "threshold_direction", "metric",
                    "owner", "override_cooldown_hours", "auto_ticket"}
        for monitor in DRIFT_MONITORS:
            missing = required - set(monitor.keys())
            assert not missing, f"Monitor {monitor['name']} missing fields: {missing}"

    def test_all_monitors_have_named_owner(self):
        for monitor in DRIFT_MONITORS:
            assert monitor["owner"], f"Monitor {monitor['name']} has no owner"
            assert monitor["owner"] != "?", f"Monitor {monitor['name']} owner is placeholder"

    def test_all_monitors_auto_ticket_is_true(self):
        for monitor in DRIFT_MONITORS:
            assert monitor["auto_ticket"] is True, \
                f"Monitor {monitor['name']}: auto_ticket must be True per drift policy"

    def test_override_cooldowns_are_positive(self):
        for monitor in DRIFT_MONITORS:
            hours = monitor["override_cooldown_hours"]
            assert hours > 0, f"Monitor {monitor['name']}: cooldown must be positive"
            assert hours <= 72, f"Monitor {monitor['name']}: cooldown > 72h is unusually long"

    def test_thresholds_are_numeric(self):
        for monitor in DRIFT_MONITORS:
            assert isinstance(monitor["threshold"], (int, float)), \
                f"Monitor {monitor['name']}: threshold must be numeric"

    def test_auth_denial_spike_has_no_auto_reversion(self):
        """Auth checks must never be automatically degraded."""
        auth_monitor = next(m for m in DRIFT_MONITORS if m["name"] == "auth_denial_spike")
        assert auth_monitor["auto_reversion_action"] is None, \
            "Auth denial spike must not have auto-reversion: auth is always enforced"

    def test_attention_fatigue_auto_reversion_threshold_above_alarm_threshold(self):
        """Auto-reversion should only trigger at a significantly higher threshold."""
        attn = next(m for m in DRIFT_MONITORS if m["name"] == "attention_fatigue")
        assert attn["auto_reversion_threshold"] > attn["threshold"], \
            "Auto-reversion threshold must be higher than alarm threshold"

    def test_confidence_miscalibration_auto_reversion_threshold_above_alarm(self):
        calib = next(m for m in DRIFT_MONITORS if m["name"] == "confidence_miscalibration")
        assert calib["auto_reversion_threshold"] > calib["threshold"], \
            "Auto-reversion threshold must be higher than alarm threshold"

    def test_monitor_names_are_unique(self):
        names = [m["name"] for m in DRIFT_MONITORS]
        assert len(names) == len(set(names)), "Monitor names must be unique"

    def test_four_monitors_defined(self):
        """Exactly 4 monitors as specified in trust-kpis-and-drift-model.md."""
        assert len(DRIFT_MONITORS) == 4, \
            f"Expected 4 drift monitors, found {len(DRIFT_MONITORS)}"


class TestTrustKPIDefinitions:
    def test_eleven_kpis_defined(self):
        """Exactly 11 KPIs as specified in trust-kpis-and-drift-model.md."""
        # decision_load_index is #11 (approval_latency_p50/p95 count as 2 informational)
        named_kpis = [k for k in TRUST_KPIS]
        assert len(named_kpis) == 12, \
            f"Expected 12 KPI entries (11 metrics + 1 split latency), found {len(named_kpis)}"

    def test_spoken_regret_rate_defined(self):
        kpi = next((k for k in TRUST_KPIS if k["name"] == "spoken_regret_rate"), None)
        assert kpi is not None, "spoken_regret_rate must be defined as a KPI"
        assert kpi["threshold"] == 0.05
        assert kpi["op"] == "<="

    def test_decision_load_index_defined(self):
        kpi = next((k for k in TRUST_KPIS if k["name"] == "decision_load_index"), None)
        assert kpi is not None, "decision_load_index must be defined as a KPI"
        assert kpi["threshold"] == 3.0

    def test_privacy_incident_count_is_hard_zero(self):
        kpi = next((k for k in TRUST_KPIS if k["name"] == "privacy_incident_count"), None)
        assert kpi is not None
        assert kpi["threshold"] == 0.0
        assert kpi["op"] == "=="

    def test_thresholds_are_in_valid_range(self):
        for kpi in TRUST_KPIS:
            if kpi["threshold"] is None:
                continue  # informational KPIs
            val = kpi["threshold"]
            assert isinstance(val, (int, float)), f"KPI {kpi['name']}: threshold must be numeric"
            assert 0.0 <= val <= 100.0, f"KPI {kpi['name']}: threshold {val} out of range"

    def test_kpi_names_are_unique(self):
        names = [k["name"] for k in TRUST_KPIS]
        assert len(names) == len(set(names)), "KPI names must be unique"


class TestDriftMonitorThresholdSanity:
    """Verify threshold values are internally consistent with trust KPIs."""

    def test_attention_fatigue_threshold_matches_interrupt_dismissal_kpi(self):
        """The attention_fatigue monitor must match the interrupt_dismissal_rate KPI threshold."""
        monitor = next(m for m in DRIFT_MONITORS if m["name"] == "attention_fatigue")
        kpi = next(k for k in TRUST_KPIS if k["name"] == "interrupt_dismissal_rate")
        assert monitor["threshold"] == kpi["threshold"], \
            "attention_fatigue threshold must match interrupt_dismissal_rate KPI threshold"

    def test_no_monitor_threshold_is_zero(self):
        """A threshold of exactly 0 would mean the monitor always fires — sanity check."""
        for m in DRIFT_MONITORS:
            assert m["threshold"] > 0, \
                f"Monitor {m['name']}: threshold of 0 would fire constantly"

    def test_cooldown_ordering_is_sensible(self):
        """Auth (urgent, 12h) < attention (24h) < calibration (48h) < memory (72h)."""
        cooldowns = {m["name"]: m["override_cooldown_hours"] for m in DRIFT_MONITORS}
        assert cooldowns["auth_denial_spike"] < cooldowns["attention_fatigue"]
        assert cooldowns["attention_fatigue"] < cooldowns["confidence_miscalibration"]
        assert cooldowns["confidence_miscalibration"] < cooldowns["memory_growth"]
