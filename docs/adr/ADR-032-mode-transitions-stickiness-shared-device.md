# ADR-032: Mode Transitions, Stickiness, and Shared-Device Ambiguity Rule

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Without explicit mode stickiness rules, modes bleed across surfaces and users, producing inconsistent privacy guarantees and authorization outcomes.

## Decision
Mode is sticky per `{user_id × surface}`. The same user holds independent modes simultaneously across surfaces. Authority precedence: EMERGENCY > OPERATOR explicit > system policy > surface default.

**Shared-device ambiguity rule:** When speaker/user identity is uncertain (voice confidence < 0.70, shared kiosk, no active session), the system MUST downgrade to FAMILY low-trust mode and suppress PERSONAL/WORK/SITE outputs until identity is confirmed.

Child/guest users are always locked to FAMILY mode. EMERGENCY overrides all surfaces for all users.

## Consequences
- Mode isolation enforced at step 6 (mode in AuthzContext)
- Mode change requires a `mode_change_reason` in ExecutionContext (audited)
- Shared-device privacy protection is a hard default, not a preference
- Spec: `docs/product/mode-transition-rules.md`
