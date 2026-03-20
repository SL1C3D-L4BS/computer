# Site Configuration Boundary

Defines all site-specific configuration, its location, and how it is consumed by core services.

## Site config location

All site-specific configuration lives in `packages/config/`. It is the only place where:
- Physical zone names appear
- Vendor-specific identifiers appear
- Location-specific data (weather zone, utility tariffs, frost dates) appears
- Asset topology is defined

## Site config structure

```
packages/config/
  versions.json              # Version pins (also used by bootstrap/CI)
  site.yaml                  # Site identity and global settings
  zones/
    greenhouse.yaml           # Greenhouse zones (dimensions, sensors, actuators)
    land.yaml                 # Land zones (field zones, boundaries)
    structures.yaml           # Structures (greenhouse buildings, outbuildings)
    network.yaml              # VLAN segments, device locations
  crops/
    spokane-frost.yaml        # WSU Spokane frost calendar
    growing-schedule.yaml     # Crop planting and harvest schedule
  tariffs/
    avista-tou.yaml           # Avista Time-of-Use tariff data
    rate-schedules.yaml       # Rate schedule tiers and windows
  assets/                    # (generated; do not edit manually)
    asset-registry.json       # Exported from digital-twin
```

## site.yaml format

```yaml
site:
  id: "spokane-01"
  name: "Spokane Homestead"
  location:
    city: "Spokane"
    state: "WA"
    country: "US"
    timezone: "America/Los_Angeles"
    usda_zone: "6b"
    elevation_ft: 1950
    lat: 47.6588
    lon: -117.4260
  mqtt:
    topic_prefix: "computer/spokane"
  integrations:
    ha_url: "${HA_URL}"           # From environment
    frigate_url: "${FRIGATE_URL}" # From environment
  features:
    osint_enabled: true
    voice_enabled: true
    robotics_enabled: true
```

Secrets are always environment variables, never in site.yaml.

## Consuming site config in services

Services load site config at startup via the config SDK:

```python
# packages/sdk/computer_sdk/config.py
from computer_sdk.config import site_config

zone = site_config.get_zone("greenhouse_zone_a")
tariff = site_config.get_current_tariff_rate()
frost_date = site_config.get_next_frost_date()
```

Services never read raw YAML files directly. They use the config SDK, which validates the config against the schema at load time.

## Swapping a site

To adapt Computer to a different physical site:
1. Replace `packages/config/` contents with the new site's data.
2. Update `data/seed/` with the new site's asset topology.
3. Update environment variables for HA URL, Frigate URL, MQTT host.
4. No changes to `apps/` or `services/` are required.

This is the definition of the site config boundary: everything physical and location-specific is in `packages/config/` and `data/seed/`.

## Version control for site config

Site config is versioned in the same monorepo as the code. This means:
- Config changes are traceable (git log).
- Config and code changes can be tested together.
- The tariff data, frost calendar, and zone definitions are part of the system's reproducible state.

Config that contains secrets (passwords, API keys) must be in `.env` files or a secrets store, never in `packages/config/`.
