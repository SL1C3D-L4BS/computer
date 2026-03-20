# Adapter Interface Contracts

Defines the interface contract every adapter must implement. Adapters are pluggable. Swapping a vendor (e.g., replacing Frigate with a different NVR) should not require changes to core services.

## Adapter types

| Adapter type | Examples | What it does |
|-------------|---------|-------------|
| Integration adapter | ha-adapter | Translates vendor entities to canonical asset events; syncs state |
| NVR/vision adapter | frigate-adapter | Translates detection events to canonical security events |
| OSINT adapter | osint-ingest | Translates external feeds to canonical incident events |
| Device adapter | (future: device-specific) | Translates raw device telemetry to canonical asset telemetry |

## Integration adapter contract

Every integration adapter must:

1. **Publish canonical events** to the MQTT event topic family:
   ```
   computer/{site}/{domain}/{asset_id}/event
   ```
   Payload must conform to `packages/contracts/event.schema.json`.

2. **Update digital-twin asset state** via the digital-twin HTTP API (not directly to Postgres):
   ```http
   PATCH /assets/{asset_id}/state
   Content-Type: application/json
   {"state": {...}, "source": "ha-adapter", "timestamp": "..."}
   ```

3. **Never publish to command_request topics**. Adapters are read-only from the hardware perspective. They receive state; they do not initiate commands.

4. **Expose a health endpoint**: `GET /health` returns `{"status": "ok", "connected_to": "...", "last_sync": "..."}`.

5. **Handle vendor reconnection**: If the vendor system (HA, Frigate) is temporarily unavailable, the adapter retries with exponential backoff and enters degraded mode (see degraded-mode-spec.md).

## HA adapter contract

Specific to `services/ha-adapter/`:

```python
class HAAdapterContract:
    def sync_entities(self) -> None:
        """
        Sync all HA entity states to digital-twin.
        Run on startup and on HA state_changed events.
        """
        pass

    def on_state_changed(self, entity_id: str, new_state: dict) -> None:
        """
        Receive HA state_changed event.
        Translate to canonical event.
        Publish to MQTT event topic.
        Update digital-twin.
        """
        pass

    def on_trigger(self, trigger: dict) -> None:
        """
        Receive HA automation trigger.
        Translate to canonical event.
        Publish to MQTT event topic.
        Do NOT actuate directly.
        """
        pass
```

The HA adapter must have a mapping file (`services/ha-adapter/entity_map.yaml`) that maps HA entity IDs to canonical asset IDs. This mapping is site-specific and is loaded from `packages/config/`.

## Frigate adapter contract

Specific to `services/frigate-adapter/`:

```python
class FrigateAdapterContract:
    def on_detection_event(self, event: dict) -> None:
        """
        Receive Frigate detection event (person, vehicle, animal, etc.).
        Translate to canonical SecurityEvent.
        Publish to MQTT event topic.
        Write to Postgres incident queue (via event-ingest API).
        """
        pass

    def on_review_event(self, review: dict) -> None:
        """
        Receive Frigate review event (alert/detection review).
        Update incident record.
        """
        pass
```

## OSINT adapter contract

Specific to `services/osint-ingest/`:

```python
class OSINTAdapterContract:
    """
    OSINT providers are optional. Each provider is a plugin.
    Implementing this contract makes a provider usable.
    """
    def get_provider_name(self) -> str: ...
    def get_latest_events(self, since: datetime) -> list[CanonicalOSINTEvent]: ...
    def get_health(self) -> dict: ...
```

Implemented providers: PulsePoint (fire/EMS dispatch), weather API, fire perimeter feed.

New providers can be added without touching any core service.

## Adding a new adapter

1. Create `services/{vendor}-adapter/` directory.
2. Implement the appropriate adapter contract interface.
3. Create entity mapping file (if integration adapter).
4. Add to compose stack (infra/docker/compose.adapters.yml).
5. Document in `docs/runbooks/adapters.md`.
6. Add health check to bootstrap.

The core orchestrator and digital-twin do not need to know about the new adapter. It plugs in via MQTT events and the digital-twin HTTP API.
