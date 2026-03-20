# eval-fixtures

> Behavioral evaluation fixtures: voice quality evals, assistant scenario fixtures, expectation deltas, and calibration test data.

---

## Overview

`eval-fixtures` is the **standing measurement layer** for Computer behavior. It contains:

- Voice behavioral evaluation fixtures (23 fixtures across V3/V4)
- Assistant decision scenario fixtures
- `ExpectationDelta` records from `computer expectation capture`
- Calibration reference data for trust KPI baselines

These are not one-time tests — they are a standing eval discipline run continuously by `eval-runner`.

## Contents

| Module | Description | Count |
|--------|-------------|-------|
| `voice_evals.py` | `VoiceEvalFixture` objects covering turn detection, barge-in, silence quality, spoken regret | 23 |
| `assistant_evals.py` | Assistant decision scenario fixtures | Varies |
| `expectation_deltas.jsonl` | `ExpectationDelta` records from production corrections | Grows over time |

## Voice Fixture Categories

| Category | Fixtures |
|----------|----------|
| Turn detection | `barge_in_false_positive`, `turn_detection_late_cutoff` |
| Room routing | `room_routing_mismatch`, `silence_violated_shared_room` |
| Ambiguity | `ambiguity_no_clarification`, `low_confidence_no_abstention` |
| Spoken length | `spoken_length_exceeded_personal`, `spoken_length_exceeded_family`, `emergency_length_exceeded` |
| Regret | `spoken_regret_triggered` |
| Mode-specific | `work_mode_briefing_length`, `private_content_no_room_check` |

## Adding New Fixtures

Every new MCP tool requires at least one fixture in this package (per `tool-admission-policy.md`). New fixture format:

```python
VoiceEvalFixture(
    id="fixture_id",
    description="What behavior is being tested",
    input={"utterance": "...", "mode": "PERSONAL", "room": "kitchen"},
    expected_decision="SUPPRESS",   # or INTERRUPT / DIGEST / DEFER
    expected_spoken_sentences=None, # None if should not speak
    category="silence",
)
```

## Testing

```bash
pytest packages/eval-fixtures/ -v
python3 -m pytest packages/eval-fixtures/eval_fixtures/voice_evals.py -v
```

## Contracts

- [`packages/runtime-contracts`](../runtime-contracts/) — `ExpectationDelta`, `ObservationRecord`
