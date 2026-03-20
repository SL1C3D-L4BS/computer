# ADR-022: Voice Fluency — v2 Contract and Shared-Device Rule

**Status:** Accepted  
**Date:** 2026-03-19

## Context
`voice-gateway` v1 treated all voice input uniformly without speaker identification, barge-in support, or shared-device awareness. This creates privacy risks on shared devices and poor UX.

## Decision
`voice-gateway` v2 implements barge-in, turn detection, low-confidence fallback, speaker-aware routing, and the **shared-device ambiguity rule**: when speaker identity is uncertain (`speaker_confidence < 0.70`), the system MUST downgrade to FAMILY low-trust mode and suppress PERSONAL/WORK content.

## Consequences
- Voice interactions are privacy-safe by default on shared devices
- Speaker identification gates scoped memory access
- Low-confidence ASR triggers confirmation before HIGH-risk requests
- Spec: `docs/product/voice-fluency-spec.md`
