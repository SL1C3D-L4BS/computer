# ADR-009: Device identity and broker authentication

**Date**: 2026-03-19  
**Status**: Accepted  
**Deciders**: FOUNDER_ADMIN

## Context

MQTT brokers are network-accessible. If any device can publish to any topic without authentication, a compromised Pi, a misconfigured adapter, or a man-in-the-middle attack can publish commands to actuators. This is an unacceptable security posture.

## Decision

Every device and service has a distinct identity and uses it to authenticate to the MQTT broker.

### Requirements

1. **No anonymous connections**: Mosquitto configured with `allow_anonymous false`.
2. **Per-device credentials**: Each device (Pi 5, Arduino, rover MCU, dock controller) has unique MQTT credentials. Credentials are stored in a secrets store, never in the repo.
3. **ACL enforcement**: Each device's MQTT client ID has an ACL that limits it to specific topic patterns:
   - Sensors: publish to `telemetry` and `event` topics for their asset; subscribe to `config` topics for their asset only.
   - Control services: subscribe to `command_request` for their domain; publish to `command_ack` for their domain.
   - Orchestrator: publish to `command_request`; subscribe to `command_ack` and `health`.
   - No wildcard publish on `command_request` topics for non-orchestrator clients.
4. **TLS on broker**: MQTT broker exposes port 8883 (TLS) for all external connections; 1883 only for localhost.
5. **Service-to-service auth**: orchestrator, control-api, adapters authenticate to each other via short-lived JWT tokens or mTLS.
6. **Secret rotation**: Broker passwords and API keys have documented rotation procedures.

### ACL example (Mosquitto ACL config)

```
# Orchestrator: can publish to all command_request topics
user computer-orchestrator
topic write computer/+/+/+/command_request
topic read computer/+/+/+/command_ack
topic read computer/+/+/+/health

# Greenhouse control service: only its domain
user computer-greenhouse-control
topic read computer/spokane/greenhouse/+/command_request
topic write computer/spokane/greenhouse/+/command_ack
topic write computer/spokane/greenhouse/+/telemetry

# Temperature sensor Pi: only its own asset
user computer-sensor-zone-a-temp
topic write computer/spokane/greenhouse/zone-a-temp-001/telemetry
topic write computer/spokane/greenhouse/zone-a-temp-001/health
```

## Consequences

- Compromised Pi cannot publish to valve or heater topics.
- Device credentials are managed and rotated; rotation automation documented in runbooks.
- New devices require provisioning (identity creation) before joining the system.
- This adds provisioning overhead but prevents a single compromised device from becoming an actuator.
