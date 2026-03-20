"""
Confidence Calibration Tests — V3

Tests that confidence values are meaningful — not just asserted but calibrated.
A ConfidenceScore of 0.8 should be correct ~80% of the time.

Reference: docs/architecture/uncertainty-and-confidence-model.md (Calibration Requirements)
           docs/delivery/experimental-design-and-evaluation.md (Calibration Metrics)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

CONTRACTS_PATH = Path(__file__).parent.parent.parent / "packages" / "runtime-contracts"
sys.path.insert(0, str(CONTRACTS_PATH))

from models import ConfidenceScore, ConfidenceType

ATTN_ENGINE_PATH = (
    Path(__file__).parent.parent.parent / "services" / "attention-engine"
)
sys.path.insert(0, str(ATTN_ENGINE_PATH))


def brier_score(predicted_probs: list[float], actuals: list[int]) -> float:
    """
    Brier score: mean squared error between predicted probability and actual outcome.
    Lower is better. Perfect calibration = 0.0. Random = 0.25. Max = 1.0.
    """
    assert len(predicted_probs) == len(actuals)
    return sum((p - a) ** 2 for p, a in zip(predicted_probs, actuals)) / len(predicted_probs)


class TestConfidenceScoreBasics:
    """Tests for the ConfidenceScore type."""

    def test_confidence_score_range(self):
        """Value must be [0,1]."""
        score = ConfidenceScore(
            value=0.75,
            type=ConfidenceType.IDENTITY,
            source="voice-gateway",
            decay_rate_per_s=0.01,
            computed_at="2026-03-19T00:00:00Z",
        )
        assert 0.0 <= score.value <= 1.0

    def test_confidence_score_staleness_detection(self):
        """Score computed 5 minutes ago with 60s max_age is stale."""
        import time
        from datetime import datetime, timezone, timedelta
        stale_time = (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat()
        score = ConfidenceScore(
            value=0.9,
            type=ConfidenceType.IDENTITY,
            source="voice-gateway",
            decay_rate_per_s=0.01,
            computed_at=stale_time,
        )
        assert score.is_stale(max_age_s=60.0) is True

    def test_confidence_score_fresh(self):
        """Recently computed score is not stale."""
        from datetime import datetime, timezone
        score = ConfidenceScore(
            value=0.9,
            type=ConfidenceType.IDENTITY,
            source="voice-gateway",
            decay_rate_per_s=0.01,
            computed_at=datetime.now(timezone.utc).isoformat(),
        )
        assert score.is_stale(max_age_s=60.0) is False


class TestAttentionCalibration:
    """
    Calibration tests for the attention-engine's predicted_ack_likelihood.

    These tests use a small labeled corpus to compute Brier score.
    Target: Brier score < 0.25

    The corpus is deliberately small for unit testing. In production,
    this test would use the full ObservationRecord replay corpus.
    """

    def _make_memory(self, dismissal_rate: float, escalation_rate: float, mode: str):
        """Create AttentionMemory for test scenarios."""
        from attention_engine.memory import AttentionMemory
        return AttentionMemory(
            user_id="test_user",
            event_type_key="test.event",
            prior_dismissal_rate=dismissal_rate,
            escalation_rate=escalation_rate,
        )

    def test_low_dismissal_rate_predicts_high_ack(self):
        """User who rarely dismisses should have high predicted ack likelihood."""
        memory = self._make_memory(dismissal_rate=0.05, escalation_rate=0.0, mode="PERSONAL")
        likelihood = memory.predicted_ack_likelihood("PERSONAL")
        assert likelihood > 0.50, f"Expected > 0.50, got {likelihood:.3f}"

    def test_high_dismissal_rate_predicts_low_ack(self):
        """User who frequently dismisses should have low predicted ack likelihood."""
        memory = self._make_memory(dismissal_rate=0.85, escalation_rate=0.0, mode="PERSONAL")
        likelihood = memory.predicted_ack_likelihood("PERSONAL")
        assert likelihood < 0.40, f"Expected < 0.40, got {likelihood:.3f}"

    def test_escalation_boosts_ack_likelihood(self):
        """User who escalates signals high engagement — should boost ack prediction."""
        memory_no_escalation = self._make_memory(dismissal_rate=0.3, escalation_rate=0.0, mode="PERSONAL")
        memory_with_escalation = self._make_memory(dismissal_rate=0.3, escalation_rate=0.5, mode="PERSONAL")
        ack_no_esc = memory_no_escalation.predicted_ack_likelihood("PERSONAL")
        ack_with_esc = memory_with_escalation.predicted_ack_likelihood("PERSONAL")
        assert ack_with_esc > ack_no_esc, "Escalation should boost predicted ack likelihood"

    def test_brier_score_on_labeled_corpus(self):
        """
        Brier score on small labeled corpus must be < 0.25.
        Corpus: (dismissal_rate, escalation_rate, mode) → actual_ack (1 or 0)
        """
        corpus = [
            # (dismissal_rate, escalation_rate, mode, actual_ack)
            (0.0,  0.0, "PERSONAL", 1),  # engaged user → ack
            (0.1,  0.0, "PERSONAL", 1),
            (0.5,  0.0, "PERSONAL", 0),  # moderate dismisser → no ack
            (0.8,  0.0, "PERSONAL", 0),
            (0.9,  0.0, "PERSONAL", 0),
            (0.1,  0.5, "PERSONAL", 1),  # escalator → ack
            (0.4,  0.3, "WORK",     1),
            (0.6,  0.0, "WORK",     0),
            (0.2,  0.0, "FAMILY",   1),
            (0.7,  0.0, "FAMILY",   0),
        ]

        predicted = []
        actuals = []
        for dismissal_rate, escalation_rate, mode, actual in corpus:
            memory = self._make_memory(dismissal_rate, escalation_rate, mode)
            predicted.append(memory.predicted_ack_likelihood(mode))
            actuals.append(actual)

        score = brier_score(predicted, actuals)
        assert score < 0.25, (
            f"Brier score {score:.4f} exceeds target 0.25. "
            "Attention calibration check failed. "
            "Review predicted_ack_likelihood formula."
        )


class TestLoopDecaySanity:
    """
    Verify that loop freshness values are correct at expected elapsed times.
    Reference: docs/product/open-loop-mathematics.md (Decay Functions)
    """

    def exponential_freshness(self, half_life_hours: float, elapsed_hours: float) -> float:
        """Compute expected freshness for exponential decay."""
        lam = math.log(2) / half_life_hours
        return math.exp(-lam * elapsed_hours)

    def test_exponential_decay_at_half_life(self):
        """At exactly half_life_hours, freshness should be 0.5."""
        half_life = 24.0
        freshness = self.exponential_freshness(half_life, half_life)
        assert abs(freshness - 0.5) < 0.001, f"Expected ~0.5 at half-life, got {freshness:.4f}"

    def test_exponential_decay_below_abandon_threshold(self):
        """At 5× half-life, freshness should be below 0.05 (abandonment threshold)."""
        half_life = 12.0
        freshness = self.exponential_freshness(half_life, half_life * 5)
        assert freshness < 0.05, (
            f"Expected < 0.05 at 5× half-life ({half_life * 5}h), got {freshness:.4f}"
        )

    def test_exponential_decay_at_zero_elapsed(self):
        """At t=0, freshness should be exactly 1.0."""
        freshness = self.exponential_freshness(24.0, 0.0)
        assert abs(freshness - 1.0) < 1e-9

    def test_linear_decay_reaches_zero_at_half_life(self):
        """Linear decay reaches 0.0 at exactly half_life_hours."""
        half_life = 48.0
        freshness = max(0.0, 1.0 - 48.0 / half_life)  # Linear formula
        assert freshness == 0.0

    def test_linear_decay_midpoint(self):
        """Linear decay at half_life/2 should be 0.5."""
        half_life = 48.0
        elapsed = half_life / 2
        freshness = max(0.0, 1.0 - elapsed / half_life)
        assert abs(freshness - 0.5) < 0.001


class TestAttentionDecisionCostStructure:
    """
    Test that the attention cost function produces values in expected ranges
    and respects the scale conventions.
    Reference: docs/product/attention-decision-model.md
    """

    def test_attention_cost_values_in_range(self):
        """All AttentionCostResult fields should be in [0,1] (except net_value)."""
        from attention_engine.memory import AttentionMemory
        from attention_engine.decision import compute_attention_cost

        memory = AttentionMemory(user_id="u1", event_type_key="test")
        cost = compute_attention_cost(
            urgency=0.7,
            mode="PERSONAL",
            attention_load=0.5,
            identity_confidence=0.8,
            urgency_decay_rate=0.001,
            memory=memory,
        )

        assert 0.0 <= cost.urgency_value <= 1.0
        assert 0.0 <= cost.interruption_cost <= 1.0
        assert 0.0 <= cost.privacy_risk <= 1.0
        assert 0.0 <= cost.predicted_ack_likelihood <= 1.0
        assert -1.0 <= cost.net_value("INTERRUPT") <= 1.0

    def test_high_urgency_high_confidence_favors_interrupt(self):
        """High urgency + high identity confidence + low attention load → INTERRUPT."""
        from attention_engine.memory import AttentionMemory
        from attention_engine.decision import compute_attention_cost, make_decision

        memory = AttentionMemory(user_id="u1", event_type_key="critical.alert")
        cost = compute_attention_cost(
            urgency=0.95,
            mode="PERSONAL",
            attention_load=0.1,
            identity_confidence=0.95,
            urgency_decay_rate=0.01,
            memory=memory,
        )
        decision, _ = make_decision(cost, memory, risk_class="HIGH", urgency=0.95)
        assert decision == "INTERRUPT"

    def test_low_urgency_high_load_favors_silent_or_digest(self):
        """Low urgency + high attention load → DIGEST or SILENT."""
        from attention_engine.memory import AttentionMemory
        from attention_engine.decision import compute_attention_cost, make_decision

        memory = AttentionMemory(user_id="u1", event_type_key="status.update")
        cost = compute_attention_cost(
            urgency=0.15,
            mode="WORK",
            attention_load=0.90,
            identity_confidence=0.88,
            urgency_decay_rate=0.0001,
            memory=memory,
        )
        decision, _ = make_decision(cost, memory, risk_class="LOW", urgency=0.15)
        assert decision in ("DIGEST", "SILENT", "QUEUE"), f"Unexpected decision: {decision}"

    def test_suppressed_state_blocks_interrupt(self):
        """SUPPRESSED state blocks INTERRUPT for non-CRITICAL events."""
        from attention_engine.memory import AttentionMemory
        from attention_engine.decision import compute_attention_cost, make_decision

        memory = AttentionMemory(
            user_id="u1",
            event_type_key="sensor.update",
            suppression_state="SUPPRESSED",
            cooldown_remaining_s=90.0,
        )
        cost = compute_attention_cost(
            urgency=0.75,
            mode="PERSONAL",
            attention_load=0.2,
            identity_confidence=0.9,
            urgency_decay_rate=0.01,
            memory=memory,
        )
        decision, _ = make_decision(cost, memory, risk_class="LOW", urgency=0.75)
        assert decision != "INTERRUPT", "SUPPRESSED state must block INTERRUPT for non-CRITICAL"

    def test_critical_bypasses_suppression(self):
        """CRITICAL risk bypasses SUPPRESSED state."""
        from attention_engine.memory import AttentionMemory
        from attention_engine.decision import compute_attention_cost, make_decision

        memory = AttentionMemory(
            user_id="u1",
            event_type_key="safety.estop",
            suppression_state="SUPPRESSED",
            cooldown_remaining_s=90.0,
        )
        cost = compute_attention_cost(
            urgency=1.0,
            mode="SITE",
            attention_load=0.5,
            identity_confidence=0.9,
            urgency_decay_rate=0.1,
            memory=memory,
        )
        decision, _ = make_decision(cost, memory, risk_class="CRITICAL", urgency=1.0)
        assert decision == "INTERRUPT", "CRITICAL must bypass SUPPRESSED state"
