# ADR-026: MCP is the Universal Tool Interface for Step 7a Only

**Status:** Accepted  
**Date:** 2026-03-19

## Context
Step 7 of the CRK loop conflated two distinct semantics: tool invocation (informational/advisory) and control job binding (site actuation). This conflation produces audit gaps and potential ADR-002 violations.

## Decision
Step 7 is split into two non-blurrable paths:
- **7a:** MCP tool invocation via `mcp-gateway` — personal/household/work/site-readonly tools
- **7b:** Control job binding via `orchestrator` — HIGH-consequence site-control with audit trail and approval gates

The mcp-gateway is a tool bus, not a control bus. Step 7b never goes through mcp-gateway.

## Consequences
- Drone arm is never registered as an MCP tool
- Site-control actuation always has an orchestrator job state machine record
- AI_ADVISORY may only invoke T0-T2 tools via 7a; may never create 7b jobs
