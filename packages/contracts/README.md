# contracts

> Shared TypeScript type definitions for site-control domain: job lifecycle, command dispatch, and asset state schemas.

---

## Overview

`contracts` contains the **canonical TypeScript types** for the site-control domain. Used by `control-api`, `orchestrator`, `digital-twin`, and frontend applications that consume job or asset data.

For Python CRK types, see [`packages/runtime-contracts`](../runtime-contracts/).

## Responsibilities

- Define `JobRequest`, `JobState`, `JobStatus` schemas
- Define `CommandRequest`, `CommandAck` MQTT message types
- Define `AssetSnapshot`, `AssetEvent` for digital-twin consumers
- Provide Zod schemas for runtime validation

**Must NOT:**
- Contain business logic
- Import from application services

## Type Catalog

| Type | Description |
|------|-------------|
| `JobRequest` | Input schema for site-control job submission |
| `JobState` | State machine enum: PENDING → COMPLETED/FAILED/ABORTED |
| `CommandRequest` | MQTT command dispatch message |
| `CommandAck` | MQTT command acknowledgment |
| `AssetSnapshot` | Current state of a physical site asset |
| `AssetEvent` | Normalized state-change event from any site source |

## Interfaces

TypeScript import:

```typescript
import type { JobRequest, JobState, AssetSnapshot } from '@computer/contracts';
```

## Local Development

```bash
pnpm install
pnpm build
```

## Testing

```bash
pnpm test
```
