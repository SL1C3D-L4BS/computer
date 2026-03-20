# Continuity and Follow-Up Model

**Status:** SPECIFIED  
**Owner:** `runtime-kernel` (continuity processor)  
**Contract types:** `OpenLoop`, `Commitment`, `FollowUp`, `ComputerState` in runtime-contracts  
**Depends on:** open-loop-mathematics.md, system-state-model.md, transition-and-control-model.md (Agent 4)

---

## The Mind Loop

Computer currently processes one request at a time. After a request completes, it has no memory of what it committed to, what needs follow-up, or what is pending. This is not ambient intelligence — it is a stateless service with a pleasant voice.

The **continuity model** adds the missing layer: a persistent mind loop that tracks what was started, what was promised, and what decayed without resolution.

**The three structures:**

| Structure | Represents | Lifecycle |
|-----------|-----------|-----------|
| `OpenLoop` | A tracked question, task, or situation requiring eventual resolution | Created → Resurfaced → Closed \| Abandoned |
| `Commitment` | An explicit promise made to a user ("I'll remind you...") | Created → Fulfilled \| Failed \| Cancelled |
| `FollowUp` | A scheduled check on an uncertain outcome | Created → Resolved \| Dropped |

---

## When Each Structure is Created

### OpenLoop creation triggers

1. User requests something that cannot be completed in the current interaction (e.g. "remind me when the irrigation job is done")
2. A workflow is started but not yet completed — the outcome is unknown
3. A site event occurs that requires attention but no decision has been made
4. Assistant detects a probable follow-up need from context ("you mentioned the greenhouse issue last week — is it resolved?")
5. A workflow signals a multi-step process that requires user input at a future step

### Commitment creation triggers

1. Explicit user request: "remind me tomorrow morning"
2. Workflow step requires user confirmation before proceeding (approval gate)
3. Assistant explicitly says "I will [X]" — any explicit first-person future promise

### FollowUp creation triggers

1. An action was taken but outcome is uncertain (irrigation started — did it succeed?)
2. A recommendation was made — did the user act on it?
3. A concern was raised — did the situation resolve itself?

---

## ComputerState Extensions

The `ComputerState` struct (in `packages/runtime-contracts/models.py`) now carries three new fields:

```python
open_loops:          list[OpenLoop]      # Active loops with decay state
pending_commitments: list[Commitment]    # Explicit promises not yet fulfilled
follow_up_queue:     list[FollowUp]      # Scheduled follow-up checks
```

All three use typed structures defined in `runtime-contracts/models.py`, not raw strings.

### Key typed fields on each structure

| Field | Type | Scale | Semantics |
|-------|------|-------|-----------|
| `priority_score` | `float` | [0,1] | Initial urgency × importance × recency |
| `freshness` | `float` | [0,1] | 1.0 at creation; decays per decay function |
| `decay_at` | `str` | ISO 8601 | Computed next decay checkpoint |
| `owner_confidence` | `ConfidenceScore` | [0,1] | Certainty of responsible party |

See `open-loop-mathematics.md` for decay functions and resurfacing rules.

---

## CRK Integration

The continuity model integrates into CRK steps 5 and 8:

### Step 5 (Workflow Binding)

When a durable workflow is bound, the CRK creates an `OpenLoop` linked to the workflow:

```python
loop = OpenLoop(
    id=f"loop-{request_id}",
    description=f"Workflow {workflow_id}: {intent_class}",
    user_id=ctx.user_id,
    priority_score=compute_priority(ctx.risk_class, event.urgency),
    freshness=1.0,
    decay_function="exponential",
    decay_half_life_hours=DECAY_HALF_LIFE_BY_INTENT[ctx.intent_class],
    closure_conditions=["workflow.completed", "workflow.failed", "operator.cancelled"],
    owner_confidence=ConfidenceScore(value=ctx.mode_confidence, type=ConfidenceType.IDENTITY, ...),
    resurfacing_schedule="event:workflow.completed",
    max_age_hours=MAX_LOOP_AGE_BY_INTENT[ctx.intent_class],
    min_resurfacing_interval_s=3600,
    trace_id_origin=ctx.trace_id,
)
state.open_loops.append(loop)
```

### Step 8 (Response Generation)

After generating a response, the CRK checks for implicit commitment language and creates `Commitment` objects:

```python
if response_contains_commitment(response.content):
    commitment = Commitment(
        id=f"commit-{request_id}",
        description=extract_commitment(response.content),
        user_id=ctx.user_id,
        due_at=extract_deadline(response.content),
        priority_score=1.0,  # Explicit commitments always start at max priority
        owner_confidence=effective_confidence,
        workflow_id=ctx.workflow_binding.workflow_id if ctx.workflow_binding else None,
        trace_id_origin=ctx.trace_id,
    )
    state.pending_commitments.append(commitment)
```

---

## Decay and Resurfacing

Decay runs continuously. The continuity processor (background task in `runtime-kernel`) runs every 10 minutes:

```python
async def continuity_tick(state: ComputerState) -> ComputerState:
    now_s = time.time()
    updated_loops = []
    for loop in state.open_loops:
        loop = update_freshness(loop, now_s)       # Apply decay function
        if should_abandon(loop, now_s):            # Invariant I-09 gate
            loop.status = OpenLoopStatus.ABANDONED
            await write_audit_record(loop, "ABANDONED")
        updated_loops.append(loop)
    return replace(state, open_loops=updated_loops)
```

Resurfacing is handled at step 9 (attention gate): loops with `priority_score × freshness > threshold` are candidates for inclusion in the next response or proactive delivery.

---

## GET /state Response

The `ComputerState` projection returned by `GET /state` on `runtime-kernel` now includes all three continuity structures. The response is:

```json
{
  "mode_by_surface": { ... },
  "active_workflow_ids": [...],
  "attention_load": 0.3,
  "system_health_flags": [],
  "active_emergency": false,
  "open_loops": [
    {
      "id": "loop-abc123",
      "description": "Irrigation job started 2h ago",
      "priority_score": 0.7,
      "freshness": 0.82,
      "status": "ACTIVE",
      "decay_half_life_hours": 12.0,
      "owner_confidence": { "value": 0.9, "type": "identity", ... }
    }
  ],
  "pending_commitments": [ ... ],
  "follow_up_queue": [ ... ]
}
```

---

## family-web Visibility

Open loops and commitments are visible in family-web:
- **History feed:** Closed and abandoned loops with resolution timestamps
- **Pending approvals:** Commitments with approval_required=true
- **Household state dashboard:** Count of active loops per mode/domain

---

## Verification

**Invariant I-09:** Enforced by continuity_tick. Test: `test_invariant_failure_injection.py::test_I09_loop_decay_to_abandoned`

**Metrics:**
- `open_loop_count_active` — monotoring metric; alert if > 20 for any single user
- `loop_closed_per_day` / `loop_created_per_day` — burn-down rate
- `commitment_fulfilled_rate` — target > 0.95

**Calibration test:** `tests/calibration/test_loop_decay_sanity.py` — verifies decay functions produce expected freshness values at known elapsed times.
