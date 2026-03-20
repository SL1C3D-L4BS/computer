# Memory Lifecycle Policy

**Status:** SPECIFIED  
**Owner:** `memory-service`  
**Contract types:** `MemoryEntry` (in system-state-model.md), `OpenLoop` (in runtime-contracts)  
**Depends on:** system-state-model.md (Memory State partition), open-loop-mathematics.md

---

## Design Principle

Memory without lifecycle policy is a liability. Stale memories produce wrong answers. Private memories surfaced to wrong audiences produce trust violations. Conflicting memories from inferred habits vs explicit corrections produce inconsistency.

Every memory entry belongs to exactly one class. Each class has:
- A distinct decay family and hazard function
- An archival threshold (below which memory moves to cold storage)
- A deletion threshold (below which memory is removed)
- Explicit redaction rules
- A conflict resolution rule when contradicting memories exist

---

## The Seven Memory Classes

### Class 1: Reminders

**Semantics:** Scheduled actions, appointments, time-sensitive items  
**Scope:** PERSONAL or HOUSEHOLD_SHARED  
**Decay family:** Step function → Exponential  
**Hazard function:**
```
H(t) =
  0          if t < due_at               # Fresh until due
  1.0        if t in [due_at, due_at+2h] # Maximum urgency window
  exponential_decay(half_life=6h)        # Decays after window passes
```
**Archival threshold:** freshness < 0.10 AND age > 48h after due_at  
**Deletion threshold:** age > 30 days after due_at  
**Redaction:** Archived after resolution; deleted on explicit user request  
**Conflict resolution:** Newer reminder supersedes older for same event  
**Override rule:** Explicit user statement "cancel my reminder" immediately sets status=CANCELLED

---

### Class 2: Preferences

**Semantics:** Explicit user preferences ("I prefer metric units", "call me by first name")  
**Scope:** PERSONAL  
**Decay family:** Plateau → Slow exponential  
**Hazard function:**
```
H(t) =
  0          if t < 90d   # Stays fresh for 3 months
  0.001/day               # Very slow exponential after 90 days
```
**Archival threshold:** freshness < 0.50 AND age > 365d  
**Deletion threshold:** age > 5 years without reinforcement  
**Redaction:** Superseded by new preference of same type  
**Conflict resolution:** Explicit statement always wins over inferred preference  
**Override rule:** "I've changed my mind about X" or correction immediately supersedes

---

### Class 3: Explicit Facts

**Semantics:** Facts stated directly by user ("my car is a Tesla Model 3", "sister's birthday is March 15")  
**Scope:** PERSONAL  
**Decay family:** Plateau → Slow exponential  
**Hazard function:**
```
H(t) =
  0          if t < 180d  # 6-month plateau
  0.0005/day              # Very slow decay (facts don't change often)
```
**Archival threshold:** freshness < 0.30 AND age > 3 years  
**Deletion threshold:** Explicit user deletion only; otherwise 10 years  
**Redaction:** SUPERSEDED status on correction; original preserved in audit with `superseded_by` reference  
**Conflict resolution:** Newer explicit fact of same type supersedes older  
**Override rule:** "That's no longer true" + correction creates SUPERSEDED record and new ACTIVE record

---

### Class 4: Shared Household Notes

**Semantics:** Notes visible to all household members ("we're out of milk", "plumber coming Thursday")  
**Scope:** HOUSEHOLD_SHARED  
**Decay family:** Linear → Abandon  
**Hazard function:**
```
H(t) = linear_decay(half_life=72h)  # 3-day linear decay for most household notes
```
**Exception:** Notes with explicit due dates use the Reminders decay model  
**Archival threshold:** freshness < 0.20  
**Deletion threshold:** freshness < 0.05 OR age > 14 days  
**Redaction:** Auto-archived when household event they reference is resolved  
**Conflict resolution:** Last writer wins for same note topic within 24h window  
**Override rule:** Any household member can mark a note as resolved

---

### Class 5: Work Context

**Semantics:** Work state, project context, decisions, meeting notes  
**Scope:** WORK  
**Decay family:** Exponential  
**Hazard function:**
```
H(t) = exponential_decay(half_life=7d)  # Weekly decay; work context rotates
```
**Exception:** Decisions marked `important=true` use half_life=30d  
**Archival threshold:** freshness < 0.30  
**Deletion threshold:** freshness < 0.05 AND age > 90d  
**Redaction:** Archived when project is marked closed  
**Conflict resolution:** Explicit session notes supersede auto-captured context  
**Override rule:** "Clear my work context" archives all WORK entries from active project

---

### Class 6: Site Incidents

**Semantics:** Equipment failures, safety events, calibration records, maintenance history  
**Scope:** SITE  
**Decay family:** Plateau  
**Hazard function:**
```
H(t) = 0  # Never decays — site incidents are permanent records
```
**Archival threshold:** None (kept active indefinitely)  
**Deletion threshold:** Explicit operator deletion with audit justification  
**Redaction:** Never automatically redacted; operator must request  
**Conflict resolution:** All incident records are additive; no superseding  
**Override rule:** Corrections create additive "correction" records linked to original

---

### Class 7: Inferred Habits

**Semantics:** Behavioral patterns inferred from observation ("user usually checks greenhouse at 7am")  
**Scope:** PERSONAL  
**Decay family:** Exponential with reinforcement  
**Hazard function:**
```
H(t) = exponential_decay(half_life=14d)  # Decays if not reinforced by observation
Reinforcement: H(t) resets to 0 when behavior is observed again
```
**Archival threshold:** freshness < 0.20  
**Deletion threshold:** freshness < 0.05  
**Redaction:** Immediately deleted on explicit user correction ("I don't do that anymore")  
**Conflict resolution:** Explicit user statement always wins over inferred habit  
**Override rule:** User correction immediately sets status=SUPERSEDED; reinforcement counter resets to 0

---

## Explicit User Statement Override Rule

**This rule is absolute and cannot be overridden by confidence weighting.**

When a user says:
- "That's not right" + correction → Mark existing memory SUPERSEDED; create new ACTIVE memory
- "I've changed my mind" + new preference → Mark old preference SUPERSEDED
- "Forget that" → Mark memory CANCELLED; no inference retained
- "That never happened" → Mark memory SUPERSEDED; create audit record of the correction
- "Cancel my [X]" → Mark specific memory CANCELLED

An explicit user correction has `confidence = 1.0` by definition. No system-inferred confidence value can equal or exceed this. No habit inference from subsequent behavior can restore a SUPERSEDED memory without explicit user confirmation.

---

## Archival Pipeline

Memory entries transition through these statuses:

```
ACTIVE → [archival trigger] → ARCHIVED → [deletion trigger] → DELETED
ACTIVE → [correction]       → SUPERSEDED → [30d] → DELETED
ACTIVE → [user cancels]     → CANCELLED → [7d] → DELETED
```

**Archival:** Memory moves to cold storage (compressed, queryable but not indexed). Retrieval from archive carries `from_archive=true` flag and freshness = 0.1.

**Deletion:** Hard-delete from primary store; soft-delete record retained in audit log with `deleted_reason`.

---

## Conflict Resolution Summary

| Conflict type | Resolution rule |
|---------------|-----------------|
| Two explicit facts of same type | Newer created_at wins; older = SUPERSEDED |
| Explicit fact vs inferred habit | Explicit fact always wins |
| Two inferred habits of same type | Weighted by observation_count; higher count wins |
| Two household notes on same topic | Last writer wins within 24h; both preserved beyond 24h |
| Explicit correction vs current memory | Correction always wins; current = SUPERSEDED |

---

## Redaction Policy

Redaction (permanent removal with no soft-delete record):
- Applied only on legal/compliance request or explicit user "delete everything" command
- Creates `REDACTION_EVENT` in audit log without content (records the fact of redaction, not what was redacted)
- Requires operator confirmation for SITE scope; requires user authentication for PERSONAL scope

---

## Metrics

| Metric | Target |
|--------|--------|
| Memory freshness at retrieval | > 0.50 for primary retrievals |
| Stale memory retrieval rate (freshness < 0.20) | < 5% |
| Conflict resolution accuracy | > 95% (correct resolution on test corpus) |
| Explicit override honored immediately | 100% |
| PERSONAL memory leaked to FAMILY mode | 0% |
