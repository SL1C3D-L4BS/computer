# assistant-contracts

> TypeScript and Python type definitions for the assistant reasoning layer: intent classification, routing decisions, and context assembly schemas.

---

## Overview

`assistant-contracts` defines the shared types between `context-router`, `assistant-api`, and consuming surfaces for assistant-plane interactions. These types bridge the CRK (`runtime-contracts`) and the product layer.

## Type Catalog

| Type | Description |
|------|-------------|
| `IntentClassification` | Classified intent with confidence and candidate routes |
| `RoutingDecision` | Final routing: tool / workflow / direct-response |
| `ContextWindow` | Assembled context: memory, mode, site state, user history |
| `AssistantResponse` | Structured response before CRK step 8 assembly |

## Interfaces

```typescript
import type { IntentClassification, RoutingDecision } from '@computer/assistant-contracts';
```

## Local Development

```bash
pnpm install && pnpm build
```

## Testing

```bash
pnpm test
```
