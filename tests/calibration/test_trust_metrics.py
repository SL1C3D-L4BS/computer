"""
Trust Metrics Calibration Tests — V4

Sanity tests for KPI definitions and drift monitor definitions.
These tests run without any live services — they verify structural correctness
of the trust model as documented in trust-kpis-and-drift-model.md.

Reference: docs/architecture/trust-kpis-and-drift-model.md
"""
from __future__ import annotations

import pytest


ALL_KPIS = [
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

RATE_KPIS = {
    "suggestion_acceptance_rate",
    "interrupt_dismissal_rate",
    "correction_rate",
    "override_rate",
    "loop_closure_rate",
    "clarification_rate",
    "regret_rate",
    "spoken_regret_rate",
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


class TestKPIDefinitions:
    def test_all_eleven_kpis_present(self):
        assert len(ALL_KPIS) == 12  # 12 entries: 11 metrics + approval_latency split into p50/p95
        assert "spoken_regret_rate" in ALL_KPIS
        assert "decision_load_index" in ALL_KPIS
        assert "privacy_incident_count" in ALL_KPIS

    def test_spoken_regret_rate_is_a_rate_kpi(self):
        assert "spoken_regret_rate" in RATE_KPIS

    def test_decision_load_index_is_not_a_rate_kpi(self):
        """decision_load_index is a composite index, not a rate."""
        assert "decision_load_index" not in RATE_KPIS

    def test_rate_kpi_thresholds_are_in_0_to_1_range(self):
        for kpi in RATE_KPIS:
            if kpi in THRESHOLDS:
                _, threshold = THRESHOLDS[kpi]
                assert 0.0 <= threshold <= 1.0, \
                    f"Rate KPI {kpi}: threshold {threshold} outside [0, 1]"

    def test_privacy_incident_count_threshold_is_zero(self):
        op, val = THRESHOLDS["privacy_incident_count"]
        assert op == "=="
        assert val == 0.0

    def test_spoken_regret_rate_threshold_lower_than_regret_rate(self):
        """spoken_regret is a leading indicator — threshold must be tighter than general regret."""
        _, spoken = THRESHOLDS["spoken_regret_rate"]
        _, general = THRESHOLDS["regret_rate"]
        assert spoken <= general, \
            "spoken_regret_rate threshold must be <= regret_rate threshold (tighter metric)"

    def test_suggestion_acceptance_uses_ge_operator(self):
        op, _ = THRESHOLDS["suggestion_acceptance_rate"]
        assert op == ">="

    def test_interruption_and_dismissal_use_le_operators(self):
        for kpi in ("interrupt_dismissal_rate", "correction_rate", "override_rate"):
            op, _ = THRESHOLDS[kpi]
            assert op == "<=", f"{kpi} should use <= operator"

    def test_loop_closure_uses_ge_operator(self):
        op, _ = THRESHOLDS["loop_closure_rate"]
        assert op == ">="

    def test_decision_load_index_threshold_is_3(self):
        op, val = THRESHOLDS["decision_load_index"]
        assert op == "<="
        assert val == 3.0


class TestDecisionLoadIndex:
    """Unit tests for decision_load_index calculation."""

    def _compute_load_index(self, open_decisions: int, avg_age_hours: float,
                             resolved_per_day: float) -> float:
        if resolved_per_day <= 0:
            return float("inf")
        return (open_decisions * avg_age_hours) / (resolved_per_day * 24)

    def test_low_load_is_below_threshold(self):
        """Few open decisions, high closure rate → healthy load."""
        index = self._compute_load_index(5, 4.0, 10.0)
        assert index < 1.0

    def test_high_load_exceeds_threshold(self):
        """Many open decisions, slow closure → exceeds threshold."""
        index = self._compute_load_index(50, 48.0, 2.0)
        assert index > 3.0

    def test_load_increases_with_age(self):
        base = self._compute_load_index(10, 8.0, 5.0)
        aged = self._compute_load_index(10, 16.0, 5.0)
        assert aged > base

    def test_load_decreases_with_closure_rate(self):
        slow = self._compute_load_index(10, 12.0, 2.0)
        fast = self._compute_load_index(10, 12.0, 8.0)
        assert fast < slow

    def test_zero_resolved_per_day_is_infinite_load(self):
        index = self._compute_load_index(10, 12.0, 0.0)
        assert index == float("inf")


class TestThresholdEvaluator:
    """Tests for threshold evaluation logic used in computer trust report."""

    def _passes(self, kpi: str, value: float) -> bool:
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

    def test_suggestion_acceptance_passes_at_threshold(self):
        assert self._passes("suggestion_acceptance_rate", 0.65)

    def test_suggestion_acceptance_fails_below_threshold(self):
        assert not self._passes("suggestion_acceptance_rate", 0.64)

    def test_spoken_regret_passes_at_threshold(self):
        assert self._passes("spoken_regret_rate", 0.05)

    def test_spoken_regret_fails_above_threshold(self):
        assert not self._passes("spoken_regret_rate", 0.06)

    def test_privacy_incident_passes_at_zero(self):
        assert self._passes("privacy_incident_count", 0.0)

    def test_privacy_incident_fails_at_any_nonzero(self):
        assert not self._passes("privacy_incident_count", 1.0)
        assert not self._passes("privacy_incident_count", 0.001)

    def test_decision_load_passes_below_3(self):
        assert self._passes("decision_load_index", 2.99)

    def test_decision_load_fails_above_3(self):
        assert not self._passes("decision_load_index", 3.01)

    def test_unknown_kpi_always_passes(self):
        assert self._passes("some_future_kpi", 0.5)
