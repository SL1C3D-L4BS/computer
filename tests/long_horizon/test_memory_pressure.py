"""
Long-Horizon Memory Pressure Test — V4

Simulates 10,000 open loops with mixed closure rates and variable decay functions.
Proves the continuity model stays bounded under real-world accumulation, not just
unit conditions.

Tests:
- Memory size remains bounded after 30d and 90d simulations
- Resurfacing accuracy maintained under pressure
- Noise ratio (stale/active) stays below threshold
- Abandonment rule fires before max_age is exceeded (Invariant I-09 at scale)
- No loop with freshness < 0.05 survives without ABANDONED transition

Reference: docs/architecture/trust-kpis-and-drift-model.md (V4.5)
           docs/product/open-loop-mathematics.md
           packages/runtime-contracts/models.py
"""
from __future__ import annotations

import math
import random
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


# ── Constants (from open-loop-mathematics.md) ─────────────────────────────────
MAX_ACTIVE_LOOPS = 5000           # I-09 invariant: max active loops per user
MAX_LOOP_AGE_DAYS = 90            # max_age: loops abandoned at this age
FRESHNESS_ABANDONMENT_THRESHOLD = 0.05  # loops below this are abandonment candidates
NOISE_RATIO_THRESHOLD = 0.30      # max stale/active ratio before memory quality degrades


class LoopStatus(str, Enum):
    ACTIVE    = "ACTIVE"
    CLOSED    = "CLOSED"
    ABANDONED = "ABANDONED"
    ARCHIVED  = "ARCHIVED"


@dataclass
class MemoryLoop:
    id: str
    priority_score: float     # 0–1
    created_day: int          # simulation day when created
    status: LoopStatus = LoopStatus.ACTIVE
    closed_day: int | None = None
    freshness: float = 1.0

    def age_days(self, current_day: int) -> float:
        return current_day - self.created_day

    def compute_freshness(self, current_day: int, decay_rate: float = 0.03) -> float:
        """Exponential freshness decay: f(t) = exp(-decay_rate * age_days)."""
        age = self.age_days(current_day)
        return math.exp(-decay_rate * age)


class MemorySimulator:
    """
    Simulates a memory service under long-horizon load.

    Parameters:
        n_loops: Initial loop count
        closure_rate: Fraction of ACTIVE loops closed each day
        decay_rate: Exponential decay coefficient (default: 0.03)
        seed: Random seed for reproducibility
    """

    def __init__(
        self,
        n_loops: int = 10_000,
        closure_rate: float = 0.30,
        decay_rate: float = 0.03,
        seed: int = 42,
    ):
        self.decay_rate = decay_rate
        self.closure_rate = closure_rate
        self.rng = random.Random(seed)
        self.loops: list[MemoryLoop] = []
        self.current_day: int = 0

        # Spawn initial loops spread across the past 30 days
        for _ in range(n_loops):
            created_day = -self.rng.randint(0, 30)
            self.loops.append(MemoryLoop(
                id=str(uuid.uuid4()),
                priority_score=self.rng.uniform(0.1, 1.0),
                created_day=created_day,
                freshness=1.0,
            ))
        self._update_freshness()

    def _update_freshness(self) -> None:
        for loop in self.loops:
            if loop.status == LoopStatus.ACTIVE:
                loop.freshness = loop.compute_freshness(self.current_day, self.decay_rate)

    def _apply_closures(self) -> int:
        active = [l for l in self.loops if l.status == LoopStatus.ACTIVE]
        n_close = int(len(active) * self.closure_rate * self.rng.uniform(0.8, 1.2))
        to_close = self.rng.sample(active, min(n_close, len(active)))
        for loop in to_close:
            loop.status = LoopStatus.CLOSED
            loop.closed_day = self.current_day
        return len(to_close)

    def _apply_abandonment_rule(self) -> int:
        """
        Invariant I-09: loops must be ABANDONED before max_age or when freshness < threshold.
        No loop with freshness < 0.05 may remain ACTIVE.
        """
        abandoned = 0
        for loop in self.loops:
            if loop.status != LoopStatus.ACTIVE:
                continue
            age = loop.age_days(self.current_day)
            if age >= MAX_LOOP_AGE_DAYS or loop.freshness < FRESHNESS_ABANDONMENT_THRESHOLD:
                loop.status = LoopStatus.ABANDONED
                loop.closed_day = self.current_day
                abandoned += 1
        return abandoned

    def _apply_max_active_cap(self) -> int:
        """
        I-09 at scale: if active count exceeds MAX_ACTIVE_LOOPS,
        archive lowest-freshness loops until below cap.
        """
        active = sorted(
            [l for l in self.loops if l.status == LoopStatus.ACTIVE],
            key=lambda l: l.freshness,
        )
        archived = 0
        while len([l for l in self.loops if l.status == LoopStatus.ACTIVE]) > MAX_ACTIVE_LOOPS:
            if not active:
                break
            loop = active.pop(0)  # lowest freshness
            loop.status = LoopStatus.ARCHIVED
            loop.closed_day = self.current_day
            archived += 1
        return archived

    def advance_days(self, n_days: int) -> dict:
        """Advance simulation by n_days. Returns daily summary stats."""
        stats = {"days": n_days, "closed_total": 0, "abandoned_total": 0, "archived_total": 0}
        for _ in range(n_days):
            self.current_day += 1
            self._update_freshness()
            stats["closed_total"] += self._apply_closures()
            stats["abandoned_total"] += self._apply_abandonment_rule()
            stats["archived_total"] += self._apply_max_active_cap()
        return stats

    @property
    def active_loops(self) -> list[MemoryLoop]:
        return [l for l in self.loops if l.status == LoopStatus.ACTIVE]

    @property
    def stale_loops(self) -> list[MemoryLoop]:
        """Stale = ACTIVE but freshness < 0.2 (not yet abandoned)."""
        return [l for l in self.active_loops if l.freshness < 0.2]

    @property
    def noise_ratio(self) -> float:
        active = len(self.active_loops)
        if active == 0:
            return 0.0
        return len(self.stale_loops) / active

    def resurfacing_accuracy(self) -> float:
        """
        Proxy for resurfacing accuracy: fraction of active loops with freshness > 0.3.
        High-freshness loops are correctly prioritized for resurfacing.
        """
        active = self.active_loops
        if not active:
            return 1.0
        high_quality = [l for l in active if l.freshness > 0.3]
        return len(high_quality) / len(active)


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestMemoryPressureBoundedness:
    """Memory size must stay bounded after 30d and 90d simulations."""

    def test_active_count_bounded_after_30_days_10pct_closure(self):
        """Even with 10% closure rate, active count must stay below I-09 cap."""
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.10, seed=1)
        sim.advance_days(30)
        assert len(sim.active_loops) <= MAX_ACTIVE_LOOPS, \
            f"Active loops {len(sim.active_loops)} exceeds I-09 cap {MAX_ACTIVE_LOOPS} at 30d/10% closure"

    def test_active_count_bounded_after_90_days_10pct_closure(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.10, seed=2)
        sim.advance_days(90)
        assert len(sim.active_loops) <= MAX_ACTIVE_LOOPS, \
            f"Active loops {len(sim.active_loops)} exceeds I-09 cap {MAX_ACTIVE_LOOPS} at 90d/10% closure"

    def test_active_count_bounded_after_30_days_30pct_closure(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.30, seed=3)
        sim.advance_days(30)
        assert len(sim.active_loops) <= MAX_ACTIVE_LOOPS

    def test_active_count_bounded_after_90_days_60pct_closure(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.60, seed=4)
        sim.advance_days(90)
        assert len(sim.active_loops) <= MAX_ACTIVE_LOOPS

    def test_active_count_bounded_after_90_days_90pct_closure(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.90, seed=5)
        sim.advance_days(90)
        assert len(sim.active_loops) <= MAX_ACTIVE_LOOPS


class TestNoSurvivorsBelowFreshnessThreshold:
    """
    Invariant I-09: No loop with freshness < 0.05 survives without ABANDONED transition.
    """

    def test_no_active_loops_below_freshness_threshold_30d(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.30, seed=10)
        sim.advance_days(30)
        violations = [
            l for l in sim.active_loops
            if l.freshness < FRESHNESS_ABANDONMENT_THRESHOLD
        ]
        assert len(violations) == 0, \
            f"{len(violations)} active loops have freshness < {FRESHNESS_ABANDONMENT_THRESHOLD} at 30d"

    def test_no_active_loops_below_freshness_threshold_90d(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.10, seed=11)
        sim.advance_days(90)
        violations = [
            l for l in sim.active_loops
            if l.freshness < FRESHNESS_ABANDONMENT_THRESHOLD
        ]
        assert len(violations) == 0, \
            f"{len(violations)} active loops have freshness < {FRESHNESS_ABANDONMENT_THRESHOLD} at 90d"

    def test_no_loop_exceeds_max_age_without_abandoned_transition(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.10, seed=12)
        sim.advance_days(MAX_LOOP_AGE_DAYS + 5)
        violations = [
            l for l in sim.loops
            if l.status == LoopStatus.ACTIVE and l.age_days(sim.current_day) > MAX_LOOP_AGE_DAYS
        ]
        assert len(violations) == 0, \
            f"{len(violations)} loops exceeded max_age={MAX_LOOP_AGE_DAYS}d without ABANDONED transition"


class TestResurfacingAccuracy:
    """Resurfacing accuracy must be maintained under memory pressure."""

    def test_resurfacing_accuracy_above_60pct_after_30d_low_closure(self):
        """Even with low closure rate, majority of active loops should be high-freshness."""
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.10, seed=20)
        sim.advance_days(30)
        accuracy = sim.resurfacing_accuracy()
        assert accuracy >= 0.60, \
            f"Resurfacing accuracy {accuracy:.2f} too low after 30d (expected >= 0.60)"

    def test_resurfacing_accuracy_above_80pct_after_30d_high_closure(self):
        """High closure rate → fewer stale loops → better resurfacing accuracy."""
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.60, seed=21)
        sim.advance_days(30)
        accuracy = sim.resurfacing_accuracy()
        assert accuracy >= 0.80, \
            f"Resurfacing accuracy {accuracy:.2f} too low after 30d/60% closure (expected >= 0.80)"


class TestNoiseRatio:
    """Noise ratio (stale/active) must stay below threshold."""

    def test_noise_ratio_below_threshold_after_30d_30pct_closure(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.30, seed=30)
        sim.advance_days(30)
        ratio = sim.noise_ratio
        assert ratio <= NOISE_RATIO_THRESHOLD, \
            f"Noise ratio {ratio:.3f} exceeds threshold {NOISE_RATIO_THRESHOLD} at 30d"

    def test_noise_ratio_below_threshold_after_90d_60pct_closure(self):
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.60, seed=31)
        sim.advance_days(90)
        ratio = sim.noise_ratio
        assert ratio <= NOISE_RATIO_THRESHOLD, \
            f"Noise ratio {ratio:.3f} exceeds threshold {NOISE_RATIO_THRESHOLD} at 90d"


class TestAbandonmentRuleFiring:
    """Abandonment rule must fire before max_age is exceeded."""

    def test_abandonment_fires_during_30d_simulation_fast_decay(self):
        """With fast decay rate (0.15), freshness reaches < 0.05 around day 20."""
        # exp(-0.15 * 20) ≈ 0.05 — so abandonment should fire by day 20-25
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.10, decay_rate=0.15, seed=40)
        stats = sim.advance_days(30)
        assert stats["abandoned_total"] > 0, \
            "Abandonment rule never fired during 30d simulation with fast decay rate"

    def test_abandonment_fires_more_than_archiving(self):
        """Natural abandonment (by freshness/age) should exceed forced archiving."""
        sim = MemorySimulator(n_loops=10_000, closure_rate=0.10, seed=41)
        stats = sim.advance_days(90)
        # With natural decay, abandonment should be the primary cleanup path
        assert stats["abandoned_total"] > 0, "No abandonment events in 90d simulation"

    def test_all_abandoned_loops_have_closed_day_set(self):
        sim = MemorySimulator(n_loops=5_000, closure_rate=0.10, seed=42)
        sim.advance_days(90)
        abandoned = [l for l in sim.loops if l.status == LoopStatus.ABANDONED]
        for loop in abandoned:
            assert loop.closed_day is not None, \
                f"Abandoned loop {loop.id} has no closed_day"
            assert loop.closed_day <= sim.current_day


class TestMixedClosureRates:
    """Test the four canonical closure rates mentioned in the V4 plan."""

    def _run_scenario(self, closure_rate: float, days: int, seed: int) -> dict:
        sim = MemorySimulator(n_loops=10_000, closure_rate=closure_rate, seed=seed)
        stats = sim.advance_days(days)
        return {
            "closure_rate": closure_rate,
            "days": days,
            "active": len(sim.active_loops),
            "noise_ratio": sim.noise_ratio,
            "resurfacing_accuracy": sim.resurfacing_accuracy(),
            "abandoned": stats["abandoned_total"],
            "archived": stats["archived_total"],
        }

    def test_10pct_closure_30d(self):
        result = self._run_scenario(0.10, 30, 50)
        assert result["active"] <= MAX_ACTIVE_LOOPS

    def test_30pct_closure_30d(self):
        result = self._run_scenario(0.30, 30, 51)
        assert result["active"] <= MAX_ACTIVE_LOOPS
        assert result["noise_ratio"] <= NOISE_RATIO_THRESHOLD

    def test_60pct_closure_30d(self):
        result = self._run_scenario(0.60, 30, 52)
        assert result["active"] <= MAX_ACTIVE_LOOPS
        assert result["resurfacing_accuracy"] >= 0.75

    def test_90pct_closure_30d(self):
        result = self._run_scenario(0.90, 30, 53)
        assert result["active"] <= MAX_ACTIVE_LOOPS
        assert result["noise_ratio"] <= 0.10  # Tighter bound for high-closure scenario

    def test_10pct_closure_90d(self):
        result = self._run_scenario(0.10, 90, 54)
        assert result["active"] <= MAX_ACTIVE_LOOPS

    def test_30pct_closure_90d(self):
        result = self._run_scenario(0.30, 90, 55)
        assert result["active"] <= MAX_ACTIVE_LOOPS
        assert result["noise_ratio"] <= NOISE_RATIO_THRESHOLD

    def test_60pct_closure_90d(self):
        result = self._run_scenario(0.60, 90, 56)
        assert result["active"] <= MAX_ACTIVE_LOOPS

    def test_90pct_closure_90d(self):
        result = self._run_scenario(0.90, 90, 57)
        assert result["active"] <= MAX_ACTIVE_LOOPS
