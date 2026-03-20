# Multimodal Interaction Model

Defines the four interaction surfaces, their session models, and when each applies.

## Surfaces

| Surface | Primary modality | Session model | Available modes |
|---------|----------------|--------------|----------------|
| **voice-gateway** | Audio (wakeword → STT → TTS) | Ephemeral per activation | PERSONAL, FAMILY, EMERGENCY |
| **family-web** | Web/mobile UI | Persistent auth session | PERSONAL, FAMILY, WORK |
| **ops-web embedded chat** | Text chat | Auth session, mode locked | WORK, SITE |
| **CLI** | Text command | Stateless or short session | WORK, SITE (no memory write) |

## Voice (voice-gateway)

Voice is the **ambient surface**. It is always available in the home without opening an app.

Interaction flow:
1. Wake word detected (Porcupine, local, on-device)
2. Utterance captured (VAD + Whisper STT, local)
3. Text sent to assistant-api with `device_id` and `session_id`
4. context-router resolves mode from device location (room mapping in identity-service) and time of day
5. model-router processes with context envelope
6. Response streamed as text to voice-gateway
7. Piper TTS synthesizes and plays locally

Voice-specific constraints:
- Responses must be ≤ 3 sentences for ambient queries (configurable per context)
- Complex results (job approval, lists, maps) prompt "I've sent that to your family-web" rather than reading it aloud
- Voice never shows visual content; family-web is the visual companion
- In FAMILY mode, voice does not reveal PERSONAL information of individual members to the room

## Family-web (apps/family-web/)

Family-web is the **primary visual and async surface**.

Key views:
- Conversation history (per user, private by default; household-shared on shared screen)
- Reminder and task list
- Shared household calendar
- Grocery and shopping list
- Household notes
- Approvals queue (pending jobs from orchestrator, visible to FOUNDER_ADMIN)
- Household routine management
- Site status cards (read-only; visible to all household members in appropriate role)

family-web authenticates against identity-service. Each user has a private view and a shared household view.

Real-time: WebSocket connection to assistant-api for streaming conversation responses and live status updates.

## Ops-web embedded chat

ops-web includes a chat surface locked to WORK or SITE mode. It is purpose-built:
- WORK mode: coding help, architecture memory, repo context, runbook lookup
- SITE mode: site status, job inspection, job proposals, incident review

This is not a general assistant. It does not surface personal or household memory. It does not TTS.

## CLI

For FOUNDER_ADMIN in terminal contexts:
```bash
computer ask "what is the current greenhouse zone A humidity?"
computer propose-job irrigation_run --zone north --duration 30m
computer status
```

CLI uses short-lived sessions. Memory writes are opt-in (`--remember` flag). Useful for scripting and quick queries without opening a browser.

## Surface selection guidance

| Use case | Use this surface |
|---------|-----------------|
| Quick ambient question in the house | Voice |
| Managing household tasks and calendar | family-web |
| Reviewing and approving site jobs | ops-web or family-web (approvals queue) |
| Coding help and architecture work | ops-web chat (WORK mode) |
| Checking site status from anywhere | family-web (site status cards) |
| Scripting or automation queries | CLI |

## Response style per surface

| Surface | Max response length | Format |
|---------|-------------------|--------|
| Voice | 3 sentences (ambient) / 1 paragraph (complex) | Plain text, no lists |
| family-web | Unlimited | Markdown, cards, lists |
| ops-web chat | Unlimited | Markdown, code blocks |
| CLI | 1 screen (unless `--full`) | Plain text or JSON (`--json`) |

Response style rules are defined in `packages/persona/response-style-rules.yaml`.
