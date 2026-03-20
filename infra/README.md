# infra

> Infrastructure configuration: Ansible provisioning, Docker Compose, Kubernetes manifests, OPNsense network config, and OpenTelemetry collector setup.

---

## Overview

The `infra/` directory contains all infrastructure-as-code for deploying and operating the Computer platform on a homestead site. Production targets bare-metal/VM, not cloud-native. Kubernetes is available but not required for the primary deployment.

## Directory Structure

```
infra/
├── ansible/     — Ansible playbooks for site provisioning
├── docker/      — Docker Compose files (development and production)
├── k8s/         — Kubernetes manifests (optional production target)
├── opnsense/    — OPNsense firewall and network segmentation config
└── otel/        — OpenTelemetry Collector pipeline configuration
```

## Deployment Targets

| Target | Use case | Notes |
|--------|---------|-------|
| Docker Compose | Local development, single-node site | Primary dev target |
| Ansible + bare-metal | Site production deployment | Homestead target |
| Kubernetes | Optional multi-node production | Available but not required |

## Key Commands

```bash
# Development — start all services
docker compose -f infra/docker/docker-compose.yml up

# Ansible — provision site server
ansible-playbook -i infra/ansible/inventory.yml infra/ansible/site.yml

# OTel collector
docker compose -f infra/otel/docker-compose.otel.yml up
```

## Network Architecture

Site network is segmented via OPNsense:

| Segment | VLAN | Services |
|---------|------|---------|
| Management | VLAN 10 | Computer control plane, databases |
| IoT | VLAN 20 | HA, sensors, actuators |
| Cameras | VLAN 30 | Frigate, NVR |
| Robotics | VLAN 40 | Rover, drone, ROS2 |
| Trusted | VLAN 50 | Operator devices |

## Observability Pipeline

OpenTelemetry Collector configuration in `otel/`:

- Receives traces from all services (OTLP gRPC)
- Routes to local Jaeger (development) or production APM
- Spanmetrics connector for derived Prometheus metrics
- Servicegraph connector for dependency topology

## Security

- All inter-service communication on management VLAN
- No IoT/camera VLAN has internet access
- Firewall rules in `opnsense/` block lateral movement
- Secrets in Ansible vault; never in Docker Compose files committed to repo
