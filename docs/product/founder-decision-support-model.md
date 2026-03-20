# Founder Decision Support Model

**Status:** SPECIFIED  
**Owner:** `mcp-gateway` (tool registration), `services/assistant-tools/` (implementation)  
**Contract types:** `DecisionRationale`, `ConfidenceScore`, `OpenLoop` in runtime-contracts  
**Depends on:** objective-functions.md (Domain 4), open-loop-mathematics.md

---

## Design Principle

Founder mode does not aggregate information — it optimizes **decision throughput**. The difference matters:

- Information aggregation: "here is everything that happened"
- Decision support: "here is what requires your decision, ranked by deadline and cost of delay"

A founder briefing that reports 40 items but results in 2 decisions resolved is a failure. A briefing that reports 8 items and results in 7 decisions resolved is a success.

**Objective function (Domain 4):**
- Maximize: `decisions_resolved_per_session`, `backlog_burn_down_rate`
- Minimize: `unresolved_decision_load`, `context_switch_cost`, `mean_decision_age_hours`

---

## Decision Classification

Every item surfaced in founder mode must be classified into one of four tiers:

| Tier | Criteria | Presentation priority |
|------|----------|-----------------------|
| **T1: Action Required** | Deadline within 24h, or `priority_score × freshness > 0.7` | First; always shown |
| **T2: Stale Decisions** | `freshness < 0.3` OR `mean_decision_age_hours > 48` | Second; truncated if queue overloaded |
| **T3: Monitoring** | No decision needed; awareness only | Third; collapsed by default |
| **T4: Background** | Long-running context (repo state, metrics trends) | On-demand only |

**Briefing truncation rule:** When `unresolved_decision_load > 20`, show only T1 items. No T2 or T3 items in overloaded state. The system must surface this explicitly: "You have 28 pending items. Showing the 8 that require action today."

---

## Decision Register

The decision register is the canonical record of founder-mode decisions. It is not a TODO list — it is a typed, queryable history that enables the reflection-engine to identify decision pattern drift.

Every `decisions.register` call creates:

```python
@dataclass
class DecisionRecord:
    id:              str      # Stable UUID
    decision:        str      # What was decided
    context:         str      # Why this decision was made
    rationale:       str      # The reasoning chain
    confidence:      float    # [0,1] founder's stated confidence at decision time
    alternatives:    list[str]  # Other options considered
    outcome:         str | None = None   # Filled in later: "correct" | "incorrect" | "unknown"
    decided_at:      str      # ISO 8601
    reviewed_at:     str | None = None   # When outcome was assessed
    decision_age_at_review_hours: float | None = None
```

**Outcome tracking:** Founder mode surfaces decisions for retrospective review at 7d, 30d, and 90d. This feeds the reflection-engine's calibration of `ToolRecommendationConfidence`.

---

## Founder Tools (registered in mcp-gateway as T2 trust tier)

### `briefing.daily`

**Purpose:** Ranked decision agenda for the current session  
**Optimization target:** Minimize `context_switch_cost`; surface only what requires a decision  
**outputSchema:**
```json
{
  "briefing_date": "ISO8601",
  "decision_load": { "t1_count": int, "t2_count": int, "total": int },
  "action_required": [{ "id": str, "description": str, "deadline": str, "urgency": float, "context": str }],
  "stale_decisions": [{ "id": str, "description": str, "age_hours": float, "freshness": float }],
  "monitoring": [{ "id": str, "summary": str }],
  "metrics": {
    "open_loops": int,
    "pending_commitments": int,
    "decisions_resolved_last_7d": int,
    "backlog_burn_down_rate": float
  },
  "decision_rationale": { ... }
}
```

### `decisions.register`

**Purpose:** Append a decision to the register with full context  
**Optimization target:** Maximize `decision_context_quality` (enables later reflection)  
**outputSchema:**
```json
{
  "decision_id": str,
  "recorded_at": str,
  "decision": str,
  "context": str,
  "rationale": str,
  "confidence": float,
  "alternatives": [str],
  "confirmation": "recorded"
}
```

### `context.load_repo`

**Purpose:** Load current codebase/workstream context into working memory scope  
**Optimization target:** Minimize cold-start context cost for technical decisions  
**outputSchema:**
```json
{
  "context_id": str,
  "scope": "WORK",
  "loaded_at": str,
  "items_loaded": int,
  "summary": str,
  "expiry_at": str,
  "decision_rationale": { ... }
}
```

### `loops.open_for_founder`

**Purpose:** Query open loops in founder mode with decay-weighted ranking  
**Optimization target:** Surface highest-priority stale loops first  
**outputSchema:**
```json
{
  "loops": [
    {
      "id": str,
      "description": str,
      "effective_priority": float,
      "freshness": float,
      "age_hours": float,
      "owner_confidence": float,
      "resurfacing_recommendation": str
    }
  ],
  "total_active": int,
  "abandonment_candidates": int,
  "decision_rationale": { ... }
}
```

---

## Briefing Composition Algorithm

```python
def compose_briefing(state: ComputerState, register: list[DecisionRecord]) -> Briefing:
    load = len(state.open_loops) + len(state.pending_commitments)

    # Rank by effective priority (priority_score × freshness)
    ranked_loops = sorted(
        [l for l in state.open_loops if l.status == OpenLoopStatus.ACTIVE],
        key=lambda l: l.priority_score * l.freshness,
        reverse=True
    )

    t1 = [l for l in ranked_loops if l.priority_score * l.freshness > 0.7]
    t2 = [l for l in ranked_loops if l.freshness < 0.3 and l not in t1]

    # Apply truncation rule
    if load > OVERLOAD_THRESHOLD:
        return Briefing(action_required=t1, stale=[], monitoring=[], truncated=True)

    return Briefing(action_required=t1, stale=t2[:10], monitoring=get_monitoring(state))
```

---

## Queue Theory Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| `unresolved_decision_load` | `len(open_loops) + len(pending_commitments)` | < 20 |
| `mean_decision_age_hours` | `mean(age_hours for all ACTIVE loops)` | < 48h (T1 tier) |
| `backlog_burn_down_rate` | `loops_closed_per_day / loops_created_per_day` | > 1.0 |
| `context_switch_cost` | `session_interruptions / decisions_resolved` | < 0.5 |
| `briefing_resolution_ratio` | `decisions_resolved / items_shown` | > 0.5 |

When `backlog_burn_down_rate < 1.0` for 3 consecutive days, the system alerts the founder once: "Decision backlog is growing faster than it's being resolved."

---

## Integration with Reflection Engine

The decision register feeds the reflection-engine's pattern analysis:

1. **Decision age drift:** Are decisions getting older before resolution? → attention model may need tuning
2. **Low-confidence decisions:** Are recurring decisions being made with low confidence? → context quality may be poor
3. **Outcome calibration:** Do high-confidence decisions have better outcomes than low-confidence ones? → if not, confidence model is miscalibrated
4. **Loop abandonment patterns:** Are specific types of loops repeatedly abandoned? → either priority scoring is wrong or the task is genuinely unresolvable

All reflection-engine proposals for founder mode changes require `operator_approved = true` (invariant I-10).
