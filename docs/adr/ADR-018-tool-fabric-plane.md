# ADR-018: Tool Fabric Plane — MCP as Universal Step 7a Interface

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Tool invocation was scattered across multiple ad-hoc HTTP integrations with no uniform auth, schema, or policy model. MCP 2025-06-18 provides structured output, OAuth 2.1 auth, and typed tool manifests.

## Decision
MCP 2025-06-18 is the universal tool interface for CRK **step 7a only**. All personal/household/work/site-readonly tool access goes through `packages/mcp-gateway/`. Direct actuation never goes through this layer (step 7b → orchestrator).

## Consequences
- Uniform `outputSchema`/`structuredContent` for all tool responses
- OAuth 2.1 auth discovery chain (RFC 9728 / RFC 8414 / RFC 8707)
- Policy function governs access — not ordering comparison
- Drone arm is never registered (ADR-002, ADR-005)
