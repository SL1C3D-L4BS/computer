"""
Seed the digital twin with Spokane site assets.
Loads from data/seed/assets.yaml (relative to repo root).

Usage:
  uv run python -m digital_twin.seed
  or via bootstrap.sh after digital-twin is running
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx
import structlog
import yaml

logger = structlog.get_logger(__name__)

DIGITAL_TWIN_URL = os.getenv("DIGITAL_TWIN_URL", "http://localhost:8001")

# Resolve seed file relative to repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.parent
SEED_FILE = _REPO_ROOT / "data" / "seed" / "assets.yaml"


def load_seed_assets() -> list[dict]:
    """Load asset definitions from YAML seed file."""
    if not SEED_FILE.exists():
        logger.warning("seed_file_not_found", path=str(SEED_FILE))
        return []

    with open(SEED_FILE) as f:
        data = yaml.safe_load(f)

    return data.get("assets", [])


def normalize_asset(raw: dict) -> dict:
    """
    Convert YAML seed format to API create request format.
    Strips vendor_entity (adapter-only field) and normalizes state.
    """
    state = raw.get("state", {})
    if isinstance(state, dict):
        value = state.get("value")
    else:
        value = str(state)

    return {
        "asset_id": raw["asset_id"],
        "name": raw["name"],
        "asset_type": raw["asset_type"],
        "capabilities": raw.get("capabilities", []),
        "zone": raw.get("zone"),
        "current_state": {"value": value} if value is not None else {},
        "qualification_level": raw.get("qualification_level", "QA0"),
        "metadata": raw.get("metadata", {}),
    }


async def seed_assets() -> dict[str, str]:
    """
    POST each asset to digital-twin API.
    Skips assets that already exist (idempotent).
    Returns dict of {asset_id: "created" | "skipped" | "error"}.
    """
    assets = load_seed_assets()
    if not assets:
        logger.warning("no_assets_to_seed")
        return {}

    results: dict[str, str] = {}

    async with httpx.AsyncClient(base_url=DIGITAL_TWIN_URL, timeout=30.0) as client:
        for raw in assets:
            asset_id = raw.get("asset_id", "unknown")
            try:
                normalized = normalize_asset(raw)

                # Check if asset already exists
                existing = await client.get(f"/assets/{asset_id}")
                if existing.status_code == 200:
                    logger.debug("asset_already_exists", asset_id=asset_id)
                    results[asset_id] = "skipped"
                    continue

                # Create the asset
                resp = await client.post("/assets", json=normalized)
                if resp.status_code in (200, 201):
                    logger.info("asset_seeded", asset_id=asset_id)
                    results[asset_id] = "created"
                else:
                    logger.error(
                        "asset_seed_failed",
                        asset_id=asset_id,
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    results[asset_id] = "error"

            except Exception as e:
                logger.error("asset_seed_exception", asset_id=asset_id, error=str(e))
                results[asset_id] = "error"

    created = sum(1 for v in results.values() if v == "created")
    skipped = sum(1 for v in results.values() if v == "skipped")
    errors = sum(1 for v in results.values() if v == "error")
    logger.info(
        "seed_complete",
        created=created,
        skipped=skipped,
        errors=errors,
        total=len(results),
    )
    return results


if __name__ == "__main__":
    results = asyncio.run(seed_assets())
    for asset_id, status in results.items():
        print(f"  {status:8s}  {asset_id}")
