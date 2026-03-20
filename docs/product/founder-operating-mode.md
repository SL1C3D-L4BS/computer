# Founder Operating Mode

**Status:** SPECIFIED  
**Owner:** `mcp-gateway` (tool registry), `runtime-kernel` (mode context)  
**Contract types:** `DecisionRationale`, `ConfidenceScore`, `OpenLoop`, `Commitment` in runtime-contracts  
**Depends on:** founder-decision-support-model.md, objective-functions.md (Domain 4), open-loop-mathematics.md  
**Trust tier:** T2 (same as operator; not PERSONAL tier)

---

## What Founder Mode Is

Founder mode is a **decision-support interface for high-consequence operational decisions**. It is not a personal assistant feature. It operates in the context of the site and household as a whole.

In founder mode, the assistant acts as a **chief of staff**, not a conversationalist:
- Surfaces what requires a decision (not everything that happened)
- Provides context compressed for quick decision-making (not raw data dumps)
- Records decisions for accountability and reflection (not ephemeral conversation)
- Ranks pending items by time-sensitivity and cost of delay

---

## When Founder Mode Activates

Founder mode activates when:
1. User explicitly requests it ("open founder mode", "give me the briefing")
2. User surface is OPS + identity_confidence > 0.85 + mode = WORK
3. Scheduled morning briefing trigger (via workflow-runtime timer)

Founder mode does NOT activate automatically in PERSONAL or FAMILY mode. The user must be identified and in an operational context.

---

## Operational Principles

**Principle 1: Decision throughput over information density**  
Every item surfaced must require a decision or be explicitly flagged as monitoring-only.

**Principle 2: Queue health visibility**  
Founder always knows how many unresolved items exist, whether the backlog is growing or shrinking, and which items are becoming critical.

**Principle 3: Decisions are recorded, not forgotten**  
The decision register is permanent. Decisions can be reviewed, retrospectively evaluated, and pattern-analyzed.

**Principle 4: Context compression, not context loss**  
When a decision requires technical context (e.g. codebase state, incident history), it must be loadable on-demand — but is not pre-loaded into every briefing.

**Principle 5: The founder is never surprised by an emergency during a briefing**  
CRITICAL safety events bypass the briefing queue and INTERRUPT immediately, regardless of founder mode session state.

---

## The Four Founder Tools

All four tools are registered in `mcp-gateway` at trust tier T2. All produce structured output with `DecisionRationale` and `ConfidenceScore` for calibration.

### 1. `briefing.daily`

Produces a ranked decision agenda for the current session.

**Input:** User ID, optional date override  
**Output:** Structured briefing with T1/T2/T3 items, queue health metrics, and action recommendations

**Truncation:** When `unresolved_decision_load > 20`, briefing shows T1 only with explicit overload notice.

### 2. `decisions.register`

Appends a decision to the permanent decision register.

**Input:** Decision text, context, rationale, confidence, alternatives  
**Output:** Decision record ID, confirmation, follow-up schedule

**Required fields:** `decision`, `context`, `rationale` — all must be non-empty.  
**Optional:** `alternatives`, `confidence` — defaults to 0.5 if not provided.

### 3. `context.load_repo`

Loads current codebase/workstream context into working memory scope for technical decisions.

**Input:** Scope key (e.g. "computer/v3", "greenhouse/irrigation")  
**Output:** Summary of loaded context, item count, expiry time

**Expiry:** Context loads expire after 60 minutes. User is notified at expiry. Re-load requires explicit command.

### 4. `loops.open_for_founder`

Returns open loops ranked by `priority_score × freshness`, specifically filtered for founder-relevant items.

**Input:** User ID, optional filter (domain, status, minimum effective priority)  
**Output:** Ranked loop list with abandonment candidates highlighted

---

## Briefing Format

The daily briefing follows a strict format to minimize scan time:

```
BRIEFING — {date} — {N} items requiring decision, {M} monitoring

ACTION REQUIRED (T1):
  1. [description] — due {deadline} — priority {score}
  2. [description] — due {deadline} — priority {score}

STALE DECISIONS (T2):
  3. [description] — {age_hours}h stale — freshness {pct}%

MONITORING (T3):
  - [summary item]

QUEUE HEALTH:
  Open loops: {N} | Commitments: {M} | Burn-down rate: {rate} ({status})
  → {recommendation if burn_rate < 1.0}
```

If queue is overloaded (`unresolved > 20`): T2 and T3 sections are suppressed. Explicit notice shown.

---

## Decision Register Schema

```
DecisionRecord {
  id:           str      # Stable UUID
  decision:     str      # What was decided (required)
  context:      str      # Why this decision was made (required)
  rationale:    str      # Reasoning chain (required)
  confidence:   float    # [0,1] founder's stated confidence
  alternatives: [str]    # Other options considered
  decided_at:   str      # ISO 8601
  outcome:      str?     # Filled retrospectively: "correct" | "incorrect" | "unknown"
  reviewed_at:  str?     # When outcome was assessed
}
```

Decisions are reviewed at 7d, 30d, and 90d retrospective checkpoints. This powers reflection-engine's calibration analysis.

---

## Integration with Reflection Engine

The decision register feeds the reflection-engine's pattern analysis:
- Decision age at review: are decisions being resolved quickly or languishing?
- Confidence calibration: do high-confidence decisions have better outcomes?
- Loop abandonment patterns: which categories of loops repeatedly decay without resolution?

All reflection proposals are `CandidatePolicyAdjustment` with `operator_approved = false` at creation. Invariant I-10 enforces no auto-apply.

---

## Mode Transition Contract

When founder mode session ends:
1. Any open decision register entries are written to the audit log
2. Any `loops.open_for_founder` query results are discarded from working memory
3. Mode reverts to pre-session mode with `mode_change_reason = "founder_session_ended"`
4. Briefing session metrics (items resolved / items shown) are logged for calibration

---

## Security Boundary

Founder mode tools are T2 trust tier. They:
- Can read PERSONAL, WORK, and SITE memory (for decision context)
- Cannot directly actuate hardware (must create orchestrator jobs with human approval)
- Cannot modify authz policies (read-only)
- Cannot suppress CRITICAL safety alerts

Founder mode does not bypass any invariant. I-01 through I-10 are all enforced during founder mode sessions.
