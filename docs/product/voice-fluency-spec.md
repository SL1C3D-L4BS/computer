# Voice Fluency Specification

**Status:** Authoritative  
**Owner:** Product  
**ADR:** ADR-022 (Voice Fluency Plane)  
**Service:** `services/voice-gateway` v2  
**Related:** `docs/product/mode-transition-rules.md`

---

## Objective

`voice-gateway` v2 provides fluent, context-aware voice interaction. The goal is a system that feels as natural as talking to a knowledgeable person in the same room — not a command-line interface that happens to accept speech.

---

## Barge-in

The system must support **barge-in**: the user can interrupt a response mid-sentence.

**Behavior:**
- Current TTS output is stopped immediately
- The user's new input is processed from the beginning
- The interrupted response is logged as `response.barge_in` in the trace

**Barge-in triggers:**
- Wake word detected while speaking
- Voice activity detection (VAD) exceeds confidence threshold while TTS is active

**Anti-spam protection:**
- Minimum 300ms pause required between barge-in and previous turn
- Prevents audio feedback loops from self-interruption

---

## Turn Detection

Determines when the user has finished speaking.

**Signals used (in priority order):**
1. Endpoint silence: >1.5s silence after speech = turn complete
2. End-of-utterance marker from ASR model
3. Intonation: falling pitch pattern (statement) vs rising pitch (question)
4. Semantic completeness: query appears syntactically complete

**Anti-cutoff protection:**
- During complex question formation, extend silence threshold to 2.5s
- If turn ends mid-sentence (< 4 words), wait 1.5s for continuation

---

## Low-Confidence Fallback

When ASR confidence is below threshold:

```
ASR confidence ≥ 0.85 → process normally
ASR confidence 0.65–0.84 → confirm before acting
ASR confidence < 0.65 → ask user to repeat
```

**Confirmation pattern (0.65–0.84):**
```
User: "Set the irrigation to forty minutes"
System: "Just to confirm — set irrigation to 40 minutes?"
User: "Yes"
System: [processes]
```

For HIGH/CRITICAL risk requests, confirmation threshold is raised to 0.90.

---

## Speaker-Aware Routing

`voice-gateway` maintains a speaker model for each authorized household member.

**Voice print enrollment:**
- Founders/owners enroll during system setup
- Family members enroll via the `family-web` profile section
- Children and guests: no enrollment → FAMILY mode (default)

**Routing logic:**
```
Incoming audio
    ↓ Speaker identification
speaker_confidence ≥ 0.70 → identified user → route to their mode/memory
speaker_confidence < 0.70 → uncertain identity → SHARED-DEVICE AMBIGUITY RULE
speaker not enrolled → FAMILY mode (default)
```

---

## Shared-Device Ambiguity Rule

When **user identity is uncertain**, the system MUST default to the lowest safe mode.

**Triggers:**
- `speaker_confidence < 0.70`
- Multiple speakers detected in audio (overlapping voices)
- No enrolled speaker identified
- No active authenticated session on the device
- Shared kiosk or common-room voice node

**Required behavior:**

1. **Mode downgrade**: Force `InputEnvelope.mode_hint = Mode.FAMILY` (low-trust)
2. **Memory suppression**: Do not read PERSONAL, WORK, or SITE-scoped memory
3. **Tool restriction**: Do not invoke tools above T1 (informational only)
4. **Output suppression**: Do not speak PERSONAL or WORK content aloud
5. **Confirmation prompt**: Before granting scoped access, require identity confirmation

**Confirmation flow:**
```
[uncertain identity detected on kitchen voice node]
→ system: "I'm not sure who I'm talking to. For personal requests, say your name or confirm in the app."
→ [user says name / confirms in app / enters PIN]
→ identity confirmed → mode = PERSONAL (or appropriate)
→ proceed with original request
```

**Security rationale:**
A household voice device is a shared physical resource. Defaulting to the least-privilege mode when identity is uncertain prevents accidental disclosure of sensitive information (schedules, financial summaries, medical reminders) to unintended listeners.

This rule is also specified in `docs/product/mode-transition-rules.md` (Shared-Device Ambiguity Rule section).

---

## Privacy Suppression

`voice-gateway` must suppress certain output categories in specific contexts.

| Context | Suppressed |
|---------|-----------|
| FAMILY mode, shared device | PERSONAL memory contents, WORK tasks, financial summaries |
| EMERGENCY mode | All non-emergency content |
| Public/guest context | All personal and household data |
| Children present (inferred from room ID or voice ID) | Adult-only content |

**Implementation:** `voice-gateway` checks `ExecutionContext.mode` from the response and applies suppression rules before TTS rendering. It does NOT make authorization decisions — it enforces output filtering based on the already-decided mode.

---

## Room Routing

`voice-gateway` v2 supports multiple voice nodes in different rooms.

**Node configuration:**
```yaml
voice_nodes:
  - node_id: "kitchen-node-01"
    room_id: "kitchen"
    default_mode_hint: FAMILY  # Kitchen is shared
    speaker_id_enabled: true

  - node_id: "office-node-01"
    room_id: "office"
    default_mode_hint: WORK
    speaker_id_enabled: true
    require_auth_for_personal: true
```

**Routing:** A request from `kitchen-node-01` defaults to FAMILY mode unless the user is identified with high confidence.

---

## v2 voice-gateway InputEnvelope additions

```python
@dataclass
class VoiceInputMetadata:
    speaker_confidence: float           # 0.0–1.0 voice print match confidence
    ambient_noise_db: float             # Ambient noise level in dB
    is_barge_in: bool                   # True if interrupted previous response
    turn_detection_confidence: float    # 0.0–1.0 end-of-turn confidence
    room_id: str                        # e.g. "kitchen", "office", "greenhouse"
    identified_speaker_id: str | None   # None if uncertain
    asr_confidence: float               # 0.0–1.0 ASR transcription confidence
```

This metadata is added to `InputEnvelope.metadata` by `voice-gateway`.  
`context-router` consumes it at step 3 to confirm mode and identity.  
`runtime-kernel` enforces the shared-device ambiguity rule based on `identified_speaker_id`.
