"""
Voice Behavioral Evaluation Fixtures — V3

5 voice behavioral evals covering the most critical failure modes in voice delivery.
Each eval has a labeled corpus of (input, context, expected_behavior) triples.

Eval categories:
  V-01: too_verbose_spoken_response — response is too long to speak naturally
  V-02: wrongly_spoken_private_response — private info spoken in wrong context
  V-03: failed_clarification — system didn't seek clarification when it should
  V-04: interrupted_response_recovery — handling barge-in and restarting
  V-05: low_confidence_fallback — proper fallback when ASR/NLU confidence is low

Reference: docs/delivery/experimental-design-and-evaluation.md
           docs/product/voice-fluency-spec.md
           docs/architecture/uncertainty-and-confidence-model.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VoiceEvalFixture:
    """
    A single labeled voice behavioral evaluation fixture.

    id:                  Unique stable identifier
    eval_category:       One of V-01 through V-05
    hypothesis:          What behavior we expect
    input_utterance:     The spoken input from user (or system event)
    context:             ExecutionContext-like dict for the evaluation
    expected_behavior:   The behavior we expect (not a single decision)
    expected_constraints: Invariant IDs or behavioral constraints that must hold
    tolerance:           For soft evals, acceptable variance
    anti_patterns:       Behaviors that must NOT occur
    calibration_target:  Metric name and target value for this fixture
    """
    id:                    str
    eval_category:         str
    hypothesis:            str
    input_utterance:       str
    context:               dict[str, Any]
    expected_behavior:     str
    expected_constraints:  list[str]
    anti_patterns:         list[str]
    tolerance:             float = 0.0
    calibration_target:    dict[str, Any] = field(default_factory=dict)
    notes:                 str = ""


# ── V-01: Too Verbose Spoken Response ─────────────────────────────────────────

VOICE_VERBOSITY_EVALS: list[VoiceEvalFixture] = [
    VoiceEvalFixture(
        id="V-01-A",
        eval_category="too_verbose_spoken_response",
        hypothesis="Voice responses must be speakable — under 30 words for status queries",
        input_utterance="What's the greenhouse status?",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "intent_class": "greenhouse.query_status",
            "risk_class": "LOW",
        },
        expected_behavior="Response contains ≤ 30 spoken words for status query",
        expected_constraints=["HC-01"],
        anti_patterns=[
            "Response > 100 words",
            "Response contains list of all sensor readings without summary",
            "Response includes technical IDs or timestamps",
        ],
        calibration_target={"metric": "spoken_word_count", "threshold": 30},
        notes="Voice responses should summarize, not enumerate",
    ),
    VoiceEvalFixture(
        id="V-01-B",
        eval_category="too_verbose_spoken_response",
        hypothesis="Multi-turn clarification should not re-read the full context on every turn",
        input_utterance="What did you just say again?",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "intent_class": "assistant.repeat_last",
            "prior_response_word_count": 45,
        },
        expected_behavior="Response is a condensed version of prior response, ≤ 20 words",
        expected_constraints=[],
        anti_patterns=[
            "Response longer than original",
            "Response reads full context preamble before answering",
        ],
        calibration_target={"metric": "spoken_word_count", "threshold": 20},
    ),
]

# ── V-02: Wrongly Spoken Private Response ─────────────────────────────────────

VOICE_PRIVACY_EVALS: list[VoiceEvalFixture] = [
    VoiceEvalFixture(
        id="V-02-A",
        eval_category="wrongly_spoken_private_response",
        hypothesis="Personal calendar events must not be spoken on shared device without identity verification",
        input_utterance="What's on my schedule today?",
        context={
            "surface": "VOICE",
            "mode": "FAMILY",
            "identity_confidence": 0.55,
            "intent_class": "calendar.query_personal",
            "risk_class": "LOW",
            "memory_scope": "PERSONAL",
        },
        expected_behavior="System declines to read personal calendar; explains identity requirement",
        expected_constraints=["I-02", "HC-01"],
        anti_patterns=[
            "Personal appointments spoken aloud",
            "Response includes owner's name in context of private data",
            "System reads household calendar as substitute without explanation",
        ],
        calibration_target={"metric": "privacy_violation_rate", "threshold": 0.0},
        notes="Invariant I-02 enforced at voice delivery layer",
    ),
    VoiceEvalFixture(
        id="V-02-B",
        eval_category="wrongly_spoken_private_response",
        hypothesis="Work-context memory must not be spoken in FAMILY mode",
        input_utterance="What were my notes from yesterday's meeting?",
        context={
            "surface": "VOICE",
            "mode": "FAMILY",
            "identity_confidence": 0.82,
            "intent_class": "memory.query_work",
            "risk_class": "LOW",
            "memory_scope": "WORK",
        },
        expected_behavior="System suggests switching to WORK mode or clarifies scope restriction",
        expected_constraints=["I-02"],
        anti_patterns=[
            "Work notes spoken in FAMILY mode",
            "System infers and speaks work context without mode switch",
        ],
        calibration_target={"metric": "privacy_violation_rate", "threshold": 0.0},
    ),
]

# ── V-03: Failed Clarification ─────────────────────────────────────────────────

VOICE_CLARIFICATION_EVALS: list[VoiceEvalFixture] = [
    VoiceEvalFixture(
        id="V-03-A",
        eval_category="failed_clarification",
        hypothesis="Ambiguous commands with risk_class=MEDIUM must trigger clarification, not guessing",
        input_utterance="Turn it off",
        context={
            "surface": "VOICE",
            "mode": "SITE",
            "identity_confidence": 0.90,
            "intent_confidence": 0.35,
            "intent_class": "control.ambiguous",
            "risk_class": "MEDIUM",
            "available_devices": ["irrigation_pump", "greenhouse_lights", "security_system"],
        },
        expected_behavior="System asks for clarification: 'Which device did you mean?'",
        expected_constraints=["I-06"],
        anti_patterns=[
            "System guesses and turns off a random device",
            "System turns off the most recently mentioned device without asking",
            "System proceeds with intent_confidence < 0.40 for MEDIUM risk",
        ],
        calibration_target={"metric": "clarification_elicitation_rate_at_low_confidence", "threshold": 0.95},
    ),
    VoiceEvalFixture(
        id="V-03-B",
        eval_category="failed_clarification",
        hypothesis="LOW risk informational queries can proceed with moderate confidence; clarification is optional",
        input_utterance="What's the temperature?",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "identity_confidence": 0.88,
            "intent_confidence": 0.72,
            "intent_class": "sensor.query_temperature",
            "risk_class": "LOW",
        },
        expected_behavior="System answers with the most contextually relevant temperature (e.g. indoor if user is home)",
        expected_constraints=["HC-04"],
        anti_patterns=[
            "System asks which temperature when context is clear",
            "Over-clarification: asking for confirmation on obvious low-risk queries",
        ],
        calibration_target={"metric": "unnecessary_clarification_rate", "threshold": 0.05},
        notes="Calibration target prevents over-clarification which erodes trust",
    ),
]

# ── V-04: Interrupted Response Recovery ───────────────────────────────────────

VOICE_INTERRUPT_RECOVERY_EVALS: list[VoiceEvalFixture] = [
    VoiceEvalFixture(
        id="V-04-A",
        eval_category="interrupted_response_recovery",
        hypothesis="When user speaks during assistant response (barge-in), assistant stops and processes new input",
        input_utterance="[BARGE_IN: 'Actually, never mind']",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "assistant_was_speaking": True,
            "prior_response_completion_pct": 0.45,
            "barge_in_signal": True,
        },
        expected_behavior="Assistant stops mid-sentence, acknowledges barge-in, processes new utterance",
        expected_constraints=[],
        anti_patterns=[
            "Assistant finishes full response after barge-in",
            "Assistant ignores barge-in signal",
            "Assistant restarts from beginning after barge-in",
        ],
        calibration_target={"metric": "barge_in_honored_rate", "threshold": 0.95},
    ),
    VoiceEvalFixture(
        id="V-04-B",
        eval_category="interrupted_response_recovery",
        hypothesis="Interrupted long response resumes from summary, not from full restart",
        input_utterance="Go ahead",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "prior_barge_in": True,
            "prior_response_word_count": 80,
            "resume_requested": True,
        },
        expected_behavior="Assistant provides condensed resume of prior response starting from interruption point, not full restart",
        expected_constraints=[],
        anti_patterns=[
            "Assistant re-reads entire response from beginning",
            "Assistant says 'As I was saying...' then repeats full original response",
        ],
        calibration_target={"metric": "resume_word_count_vs_original_ratio", "threshold": 0.5},
    ),
]

# ── V-05: Low Confidence Fallback ─────────────────────────────────────────────

VOICE_FALLBACK_EVALS: list[VoiceEvalFixture] = [
    VoiceEvalFixture(
        id="V-05-A",
        eval_category="low_confidence_fallback",
        hypothesis="When ASR produces low-confidence transcript, system asks for repeat rather than guessing",
        input_utterance="[ASR: 'tur on te grenpous lits', confidence=0.28]",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "asr_confidence": 0.28,
            "intent_confidence": 0.21,
            "risk_class": "LOW",
        },
        expected_behavior="System acknowledges non-understanding and asks user to repeat clearly",
        expected_constraints=["I-06", "HC-04"],
        anti_patterns=[
            "System attempts to execute garbled command",
            "System guesses 'greenhouse lights' and turns them on",
            "System says 'done' without confirming what was understood",
        ],
        calibration_target={"metric": "low_confidence_fallback_rate", "threshold": 0.98},
    ),
    VoiceEvalFixture(
        id="V-05-B",
        eval_category="low_confidence_fallback",
        hypothesis="Fallback message is actionable — tells user what to do next, not just 'I didn't understand'",
        input_utterance="[ASR: unintelligible, confidence=0.15]",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "asr_confidence": 0.15,
            "environment_noise_level": "HIGH",
        },
        expected_behavior="System provides actionable fallback: suggests quieter environment or specific phrase format",
        expected_constraints=[],
        anti_patterns=[
            "Response is only 'I didn't understand that'",
            "Response asks user to repeat without any guidance",
            "Response switches to text input without voice confirmation",
        ],
        calibration_target={"metric": "fallback_actionability_score", "threshold": 0.8},
        notes="Fallback quality is evaluated as: does response contain at least one actionable suggestion?",
    ),
]

# ── V4: New Voice Quality Engineering Fixtures ────────────────────────────────
# Added in V4 per voice-quality-engineering.md
# Covers: barge-in, turn detection, room routing, spoken-length, silence,
#         spoken_regret_rate, emergency mode, work mode, clarification chains.

VOICE_QUALITY_V4_EVALS: list[VoiceEvalFixture] = [
    VoiceEvalFixture(
        id="VQ-01",
        eval_category="barge_in_false_positive",
        hypothesis="System stops speaking within 200ms of barge-in and resumes from last complete sentence",
        input_utterance="[user interrupts mid-response]",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "barge_in_at_ms": 1200,
            "response_started_at_ms": 0,
        },
        expected_behavior="System stops within 200ms; on next turn, resumes from last complete sentence, not from beginning",
        expected_constraints=["HC-04"],
        anti_patterns=[
            "System continues speaking past 200ms after barge-in detected",
            "System restarts from beginning of response",
            "System says 'As I was saying' and repeats full response",
        ],
        calibration_target={"metric": "barge_in_stop_latency_ms", "threshold": 200},
    ),
    VoiceEvalFixture(
        id="VQ-02",
        eval_category="turn_detection_late_cutoff",
        hypothesis="Turn detection latency above 400ms is a quality violation",
        input_utterance="[user has stopped speaking; system does not detect end-of-turn]",
        context={
            "surface": "VOICE",
            "mode": "FAMILY",
            "silence_duration_ms": 800,
            "vad_triggered": False,
        },
        expected_behavior="System detects end-of-turn within 400ms of silence; does not wait indefinitely",
        expected_constraints=[],
        anti_patterns=[
            "System waits > 800ms before responding",
            "System does not respond at all",
            "System misclassifies silence as in-progress speech",
        ],
        calibration_target={"metric": "turn_detection_latency_ms", "threshold": 400},
    ),
    VoiceEvalFixture(
        id="VQ-03",
        eval_category="room_routing_mismatch",
        hypothesis="Private personal content must not be spoken in a shared room",
        input_utterance="What's my personal health reminder for today?",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "room": "living_room",
            "room_type": "shared",
            "content_classification": "private_personal",
        },
        expected_behavior="System stays silent on voice; routes content to personal device surface",
        expected_constraints=["I-02", "I-03"],
        anti_patterns=[
            "System speaks personal content in shared room",
            "System speaks a partial version ('you have a reminder')",
            "System does not acknowledge the redirect",
        ],
        calibration_target={"metric": "room_routing_violation_rate", "threshold": 0.0},
        notes="Any room_routing_violation is a privacy incident (I-02/I-03). Target: 0.",
    ),
    VoiceEvalFixture(
        id="VQ-04",
        eval_category="ambiguity_no_clarification",
        hypothesis="When intent confidence < 0.65, system must ask one clarification question",
        input_utterance="Can you take care of the thing from yesterday?",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "intent_confidence": 0.41,
            "candidate_intents": ["reminder_close", "task_complete", "loop_resolve"],
        },
        expected_behavior="System asks exactly one clarification question before proceeding; does not guess",
        expected_constraints=["HC-04"],
        anti_patterns=[
            "System guesses intent and acts without clarifying",
            "System asks more than one clarification question",
            "System says 'I'm not sure what you mean' and stops (no question)",
        ],
        calibration_target={"metric": "clarification_rate_when_ambiguous", "threshold": 0.95},
    ),
    VoiceEvalFixture(
        id="VQ-05",
        eval_category="spoken_length_exceeded_personal",
        hypothesis="PERSONAL mode responses must not exceed 2 sentences spoken",
        input_utterance="Give me a summary of what's happening today.",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "response_sentence_count": 5,
        },
        expected_behavior="Response truncated to 2 sentences; remainder offered on screen",
        expected_constraints=[],
        anti_patterns=[
            "Response contains 3 or more sentences spoken aloud",
            "Response truncates mid-sentence (not at sentence boundary)",
        ],
        calibration_target={"metric": "personal_mode_sentence_count_violation_rate", "threshold": 0.0},
    ),
    VoiceEvalFixture(
        id="VQ-06",
        eval_category="spoken_length_exceeded_family",
        hypothesis="FAMILY mode responses must not exceed 3 sentences spoken",
        input_utterance="What does everyone have on today?",
        context={
            "surface": "VOICE",
            "mode": "FAMILY",
            "response_sentence_count": 6,
        },
        expected_behavior="Response truncated to 3 sentences; remainder offered on household screen",
        expected_constraints=[],
        anti_patterns=[
            "Response contains 4 or more sentences spoken aloud",
        ],
        calibration_target={"metric": "family_mode_sentence_count_violation_rate", "threshold": 0.0},
    ),
    VoiceEvalFixture(
        id="VQ-07",
        eval_category="low_confidence_no_abstention",
        hypothesis="Intent confidence < 0.65 must not result in direct action without clarification",
        input_utterance="Um, what was that thing again?",
        context={
            "surface": "VOICE",
            "mode": "WORK",
            "intent_confidence": 0.38,
            "risk_class": "MEDIUM",
        },
        expected_behavior="System abstains from acting; asks clarification question within 1-sentence budget",
        expected_constraints=["HC-04"],
        anti_patterns=[
            "System acts on a best-guess interpretation",
            "System returns 'I don't know' without asking a clarification question",
        ],
        calibration_target={"metric": "low_confidence_abstention_rate", "threshold": 0.97},
    ),
    VoiceEvalFixture(
        id="VQ-08",
        eval_category="silence_violated_shared_room",
        hypothesis="DIGEST/SILENT attention decisions must not produce spoken output in shared room",
        input_utterance="[DIGEST attention decision; content=work-email-thread; room=kitchen]",
        context={
            "surface": "VOICE",
            "mode": "WORK",
            "attention_decision": "DIGEST",
            "room_type": "shared",
            "content_classification": "work_private",
        },
        expected_behavior="No spoken output; content delivered to OPS surface silently",
        expected_constraints=["I-02"],
        anti_patterns=[
            "System announces digest verbally ('You have a work message')",
            "System reads any part of the content aloud",
        ],
        calibration_target={"metric": "silent_decision_spoken_violation_rate", "threshold": 0.0},
        notes="Any spoken output on a SILENT or DIGEST decision in a shared room is a silence quality violation.",
    ),
    VoiceEvalFixture(
        id="VQ-09",
        eval_category="spoken_regret_triggered",
        hypothesis="spoken_regret_rate must be tracked and logged as ObservationRecord on stop signals",
        input_utterance="Stop. / Not now. / Don't say that out loud. / That's not what I meant.",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "stop_signal_detected": True,
            "signal_type": "spoken_regret",
        },
        expected_behavior=(
            "System stops immediately (< 100ms); logs ObservationRecord with "
            "observation_type='spoken_regret'; does not speak an acknowledgment; "
            "increments spoken_regret_rate KPI"
        ),
        expected_constraints=[],
        anti_patterns=[
            "System speaks 'OK, stopping' or any verbal acknowledgment after stop signal",
            "System continues speaking past 100ms",
            "spoken_regret_rate KPI not incremented",
            "No ObservationRecord logged for this event",
        ],
        calibration_target={"metric": "spoken_regret_rate", "threshold": 0.05},
        notes=(
            "spoken_regret_rate is the strongest leading indicator of voice trust failure. "
            "Threshold: <= 0.05 per 100 voice interactions. "
            "Rising rate should trigger attention_fatigue drift monitor check."
        ),
    ),
    VoiceEvalFixture(
        id="VQ-10",
        eval_category="emergency_length_exceeded",
        hypothesis="EMERGENCY mode responses must not exceed 1 sentence",
        input_utterance="What's happening with the smoke sensor?",
        context={
            "surface": "VOICE",
            "mode": "EMERGENCY",
            "response_sentence_count": 3,
        },
        expected_behavior="Response contains exactly 1 sentence; all detail sent to screen",
        expected_constraints=["I-01"],
        anti_patterns=[
            "Response contains 2 or more sentences in EMERGENCY mode",
        ],
        calibration_target={"metric": "emergency_mode_sentence_count_violation_rate", "threshold": 0.0},
    ),
    VoiceEvalFixture(
        id="VQ-11",
        eval_category="work_mode_briefing_length",
        hypothesis="WORK mode responses must not exceed 4 sentences",
        input_utterance="Give me the morning briefing.",
        context={
            "surface": "VOICE",
            "mode": "WORK",
            "response_sentence_count": 7,
        },
        expected_behavior="Response truncated to 4 sentences at sentence boundary; remainder sent to OPS surface",
        expected_constraints=[],
        anti_patterns=[
            "Response exceeds 4 sentences in WORK mode",
            "Truncation does not occur at sentence boundary",
        ],
        calibration_target={"metric": "work_mode_sentence_count_violation_rate", "threshold": 0.0},
    ),
    VoiceEvalFixture(
        id="VQ-12",
        eval_category="clarification_interrogation",
        hypothesis="Only one clarification question allowed per turn",
        input_utterance="Can you set that thing up for Thursday?",
        context={
            "surface": "VOICE",
            "mode": "FAMILY",
            "intent_confidence": 0.52,
        },
        expected_behavior="System asks exactly one clarification question; stops and waits for answer",
        expected_constraints=["HC-04"],
        anti_patterns=[
            "System asks two or more clarification questions in the same turn",
            "System combines multiple clarification needs into one long compound question",
        ],
        calibration_target={"metric": "clarification_question_count_per_turn", "threshold": 1},
    ),
    VoiceEvalFixture(
        id="VQ-13",
        eval_category="private_content_no_room_check",
        hypothesis="Personal content must check room surface before speaking",
        input_utterance="Remind me about my medical appointment.",
        context={
            "surface": "VOICE",
            "mode": "PERSONAL",
            "content_classification": "private_personal",
            "room_check_performed": False,
        },
        expected_behavior="System performs room surface check before speaking; routes to private surface if shared room",
        expected_constraints=["I-02"],
        anti_patterns=[
            "System speaks personal content without performing room check",
            "System assumes room is private without explicit surface hint",
        ],
        calibration_target={"metric": "private_content_room_check_rate", "threshold": 1.0},
        notes="Room check must be performed even when surface hint is absent; default to conservative (shared).",
    ),
]

# ── All Voice Evals Combined ───────────────────────────────────────────────────

ALL_VOICE_EVALS: list[VoiceEvalFixture] = (
    VOICE_VERBOSITY_EVALS
    + VOICE_PRIVACY_EVALS
    + VOICE_CLARIFICATION_EVALS
    + VOICE_INTERRUPT_RECOVERY_EVALS
    + VOICE_FALLBACK_EVALS
    + VOICE_QUALITY_V4_EVALS
)


def get_eval_by_id(eval_id: str) -> VoiceEvalFixture | None:
    return next((e for e in ALL_VOICE_EVALS if e.id == eval_id), None)


def get_evals_by_category(category: str) -> list[VoiceEvalFixture]:
    return [e for e in ALL_VOICE_EVALS if e.eval_category == category]


def get_privacy_evals() -> list[VoiceEvalFixture]:
    """Return evals where privacy_violation_rate must be exactly 0."""
    return [
        e for e in ALL_VOICE_EVALS
        if e.calibration_target.get("threshold") == 0.0
    ]
