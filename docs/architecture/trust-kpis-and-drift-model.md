# Trust KPIs and Drift Model

**Status:** Active  
**Version:** 1.0.0  
**Owner:** AI eval lead + named monitor owners (see table below)

---

## Overview

Trust in Computer is not a feeling — it is a set of measurable signals. This document defines 11 Trust KPIs, their thresholds, the drift monitors that watch them, and explicit ownership for each monitor.

All KPIs are logged as `ObservationRecord` events and aggregated by `computer trust report`.

---

## 11 Trust KPIs

All thresholds are soft unless marked HARD. Exceeding a threshold triggers the associated drift monitor.

| KPI | Description | Threshold | Type |
| --- | --- | --- | --- |
| `suggestion_acceptance_rate` | Rate of suggestions the user accepts without correction | ≥ 0.65 | soft |
| `interrupt_dismissal_rate` | Rate of INTERRUPT decisions the user dismisses/ignores | ≤ 0.30 | soft |
| `correction_rate` | Rate of decisions the user explicitly corrects | ≤ 0.20 | soft |
| `approval_latency_p50` | Median time from approval request to approval action (seconds) | N/A (track) | informational |
| `approval_latency_p95` | 95th percentile approval latency | N/A (track) | informational |
| `override_rate` | Rate of operator-initiated overrides of system decisions | ≤ 0.15 | soft |
| `loop_closure_rate` | Rate of open loops closed (vs abandoned or stale) in the period | ≥ 0.70 | soft |
| `privacy_incident_count` | Count of I-02 / I-03 invariant fires (privacy violations) | = 0 | **HARD** |
| `clarification_rate` | Rate of decisions where system abstained and asked for clarification | ≤ 0.20 | soft |
| `regret_rate` | Rate of explicit "that was wrong / not now / don't do that" events, normalized by decision class | ≤ 0.10 | soft |
| `spoken_regret_rate` | Voice-specific stop/interrupt signals ("stop", "not now", "don't say that out loud"); strongest leading indicator of voice trust failure | ≤ 0.05 | soft |
| `decision_load_index` | `open_decisions × avg_decision_age / decisions_resolved_per_day`; measures whether founder mode is burning down or accumulating cognitive debt | ≤ 3.0 | soft |

---

## Drift Monitors with Ownership

Each monitor defines: threshold, owner (named role), override permission, cooldown after override, and whether a failed check auto-opens a review ticket.

| Monitor | Threshold | Owner | Override cooldown | Auto-ticket |
| --- | --- | --- | --- | --- |
| `confidence_miscalibration` | Brier score > 0.25 in any decision class | AI eval lead | 48h | Yes |
| `attention_fatigue` | `interrupt_dismissal_rate` > 0.30 averaged over 24h | Attention-engine owner | 24h | Yes |
| `memory_growth` | Open loop count growth > 5%/day for 3 consecutive days without closure | Memory-service owner | 72h | Yes |
| `auth_denial_spike` | Auth denial rate > 3x rolling 7-day baseline in any 24h window | Security/identity owner | 12h | Yes |

### Override Rules

- Any named owner may override their monitor within their cooldown window with a written reason
- Overrides within cooldown require escalation to the founder + written reason
- Consecutive overrides (> 3 in 7 days) without resolution auto-escalate to severity-1 review
- Override records are logged as `DisturbanceRecord` in the audit log

### Cooldown Enforcement

The cooldown period begins when an override is recorded. No second override may be applied to the same monitor within the cooldown window without escalation. The cooldown resets when the monitor returns to healthy range and holds for 24h.

---

## `decision_load_index` Details

```
decision_load_index = open_decisions × avg_decision_age_hours / decisions_resolved_per_day
```

Exposed via `computer founder load`. If this index is:
- **< 1.0**: Healthy — founder mode is burning down faster than accumulating
- **1.0–3.0**: Elevated — review T2 stale loops this session
- **> 3.0**: High — founder mode is accumulating debt. Prioritize abandonment decisions.

A rising `decision_load_index` over multiple days is a signal that the briefing cadence or decision throughput needs adjustment — not a signal to add more tools.

---

## KPI Logging

Every KPI event must be logged as an `ObservationRecord` with:

```python
ObservationRecord(
    observation_type="<kpi_name>",
    value=<measured_value>,
    context={"mode": ..., "domain": ..., "surface": ...},
    timestamp=<iso8601>,
    trace_id=<associated_trace_id>,
)
```

`spoken_regret_rate` events additionally carry:
- `signal_type`: "stop" | "not_now" | "dont_say_that" | "not_what_i_meant"
- `surface`: "VOICE" (always)

---

## Drift Review Cadence

The weekly drift digest ritual (`computer drift digest --period 7d`) should be run on a fixed cadence: **Monday morning**. Without the ritual, drift alerts decay into ignored logs.

See `docs/safety/drift-remediation-policy.md` for the full ritual procedure and remediation paths.
