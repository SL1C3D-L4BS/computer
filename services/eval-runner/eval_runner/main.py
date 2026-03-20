"""
Eval Runner — AI behavioral regression testing service

Runs EvalFixture corpus against the live runtime-kernel stub.
Detects regressions in CRK invariants and AI boundary behaviors.

ADR: ADR-023 (AI Evaluation Plane)
Reference: docs/delivery/assistant-eval-plan.md
"""
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
import httpx
import structlog

CONTRACTS_PATH = Path(__file__).parent.parent.parent.parent / "packages" / "runtime-contracts"
FIXTURES_PATH = Path(__file__).parent.parent.parent.parent / "packages" / "eval-fixtures"
sys.path.insert(0, str(CONTRACTS_PATH))
sys.path.insert(0, str(FIXTURES_PATH))

log = structlog.get_logger(__name__)

RUNTIME_KERNEL_URL = "http://localhost:8063"

app = FastAPI(
    title="Eval Runner",
    description="AI behavioral regression testing — eval corpus runner",
    version="0.1.0",
)

_results_cache: dict[str, dict] = {}

# ── V4: Shadow Mode State ──────────────────────────────────────────────────────
_shadow_divergence_log: list[dict] = []
_shadow_baseline_policy_version: str | None = None
_canary_active: bool = False
_canary_policy_version: str | None = None


class ShadowComparison(BaseModel):
    policy_version: str
    trace_id: str
    live_decision: str
    shadow_decision: str
    diverged: bool
    divergence_type: str | None = None
    confidence_delta: float = 0.0
    metadata: dict = {}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "eval-runner"}


@app.post("/eval/run")
async def run_fixture(body: dict[str, Any]) -> dict[str, Any]:
    """Run a single named fixture by ID."""
    fixture_id = body.get("fixture_name") or body.get("fixture_id", "")
    try:
        from eval_fixtures.corpus import FIXTURES
        fixture = FIXTURES.get(fixture_id)
        if not fixture:
            return {"error": f"Fixture '{fixture_id}' not found", "available": list(FIXTURES.keys())}
        result = await _run_fixture(fixture)
        _results_cache[fixture_id] = result
        return result
    except ImportError:
        return {"error": "eval-fixtures package not available", "fixture_id": fixture_id}


@app.post("/eval/run/category/{category}")
async def run_category(category: str) -> dict[str, Any]:
    """Run all fixtures in a category."""
    try:
        from eval_fixtures.corpus import FIXTURES
        fixtures = [f for f in FIXTURES.values() if f.get("category") == category]
        results = []
        for fixture in fixtures:
            r = await _run_fixture(fixture)
            results.append(r)
        passed = sum(1 for r in results if r["passed"])
        return {
            "category": category,
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "results": results,
        }
    except ImportError:
        return {"error": "eval-fixtures package not available"}


@app.post("/eval/run/all")
async def run_all() -> dict[str, Any]:
    """Run the complete eval corpus."""
    try:
        from eval_fixtures.corpus import FIXTURES
        results = []
        for fixture in FIXTURES.values():
            r = await _run_fixture(fixture)
            results.append(r)
        passed = sum(1 for r in results if r["passed"])
        regressions = [r["fixture_id"] for r in results if not r["passed"]]
        return {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "regressions": regressions,
            "results": results,
        }
    except ImportError:
        return {"error": "eval-fixtures package not available"}


@app.get("/eval/fixtures")
async def list_fixtures() -> dict[str, Any]:
    """List all registered fixtures."""
    try:
        from eval_fixtures.corpus import FIXTURES
        return {
            "fixtures": [
                {"id": fid, "category": f.get("category"), "description": f.get("description")}
                for fid, f in FIXTURES.items()
            ],
            "count": len(FIXTURES),
        }
    except ImportError:
        return {"fixtures": [], "count": 0, "note": "eval-fixtures not available"}


@app.post("/eval/shadow")
async def shadow_compare(comparison: ShadowComparison) -> dict[str, Any]:
    """
    V4 Shadow Mode: compare live vs shadow policy decisions.

    Accepts a ShadowComparison and logs divergences for operator review.
    POST /eval/shadow

    Returns: {logged: bool, divergence_id: str | None}
    """
    divergence_id = None
    if comparison.diverged:
        divergence_id = f"div-{uuid.uuid4().hex[:8]}"
        record = {
            "divergence_id": divergence_id,
            "trace_id": comparison.trace_id,
            "type": comparison.divergence_type or "unknown",
            "live": comparison.live_decision,
            "shadow": comparison.shadow_decision,
            "policy_version": comparison.policy_version,
            "confidence_delta": comparison.confidence_delta,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metadata": comparison.metadata,
        }
        _shadow_divergence_log.append(record)
        log.info("eval_runner.shadow_divergence", **record)

    return {
        "logged": True,
        "diverged": comparison.diverged,
        "divergence_id": divergence_id,
        "total_divergences": len(_shadow_divergence_log),
    }


@app.get("/eval/shadow/divergences")
async def shadow_divergences(
    limit: int = 50,
    type: str | None = None,
) -> dict[str, Any]:
    """
    V4 Shadow Mode: list divergence log.
    GET /eval/shadow/divergences?limit=50&type=attention|routing|tool_selection
    """
    entries = _shadow_divergence_log
    if type:
        entries = [d for d in entries if d.get("type") == type]
    entries = entries[-limit:]
    return {
        "divergences": entries,
        "total": len(_shadow_divergence_log),
        "filtered_type": type,
    }


@app.post("/eval/shadow/baseline/freeze")
async def shadow_baseline_freeze(body: dict[str, Any] = {}) -> dict[str, Any]:
    """
    V4 Shadow Mode: freeze current policy as baseline.
    POST /eval/shadow/baseline/freeze → pins policy_version for clean A/B comparison.
    """
    global _shadow_baseline_policy_version
    _shadow_baseline_policy_version = body.get("policy_version", f"baseline-{uuid.uuid4().hex[:8]}")
    log.info("eval_runner.baseline_frozen", policy_version=_shadow_baseline_policy_version)
    return {
        "frozen": True,
        "policy_version": _shadow_baseline_policy_version,
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


@app.get("/eval/shadow/canary/status")
async def shadow_canary_status() -> dict[str, Any]:
    """
    V4 Shadow Mode: canary rollout health.
    GET /eval/shadow/canary/status
    """
    return {
        "canary_active": _canary_active,
        "canary_policy_version": _canary_policy_version,
        "baseline_policy_version": _shadow_baseline_policy_version,
        "divergence_count": len(_shadow_divergence_log),
        "high_confidence_divergences": sum(
            1 for d in _shadow_divergence_log if d.get("confidence_delta", 0) > 0.20
        ),
    }


async def _run_fixture(fixture: dict) -> dict[str, Any]:
    """Execute a single EvalFixture against runtime-kernel."""
    t0 = time.monotonic()
    fixture_id = fixture.get("id", "unknown")
    failures = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            envelope = fixture.get("input_envelope", {})
            if not envelope.get("trace_id"):
                envelope["trace_id"] = f"eval-{uuid.uuid4().hex[:8]}"

            r = await client.post(f"{RUNTIME_KERNEL_URL}/execute", json=envelope)

            if r.status_code != 200:
                return {
                    "fixture_id": fixture_id,
                    "category": fixture.get("category"),
                    "passed": False,
                    "failures": [f"runtime-kernel returned {r.status_code}: {r.text[:200]}"],
                    "elapsed_ms": int((time.monotonic() - t0) * 1000),
                }

            body = r.json()

            # Check: must_not_contain
            for phrase in fixture.get("must_not_contain", []):
                if phrase.lower() in str(body).lower():
                    failures.append(f"Response contains forbidden phrase: {phrase!r}")

            # Check: expected_7b_is_noop
            if fixture.get("expected_7b_is_noop"):
                if body.get("proposed_jobs"):
                    failures.append(
                        f"Step 7b must be noop but got jobs: {body['proposed_jobs']}"
                    )

            # Check: expected_proposed_jobs empty
            expected_jobs = fixture.get("expected_proposed_jobs")
            if expected_jobs == [] and body.get("proposed_jobs"):
                failures.append(f"Expected no jobs but got: {body['proposed_jobs']}")

            # Check: trace_id preserved
            sent_trace = envelope.get("trace_id")
            if body.get("trace_id") != sent_trace:
                failures.append(
                    f"trace_id mismatch: sent={sent_trace!r}, got={body.get('trace_id')!r}"
                )

    except Exception as e:
        failures.append(f"Exception: {e}")

    elapsed = int((time.monotonic() - t0) * 1000)
    passed = len(failures) == 0
    log.info("eval_runner.result", fixture_id=fixture_id, passed=passed,
             failures=len(failures), elapsed_ms=elapsed)

    return {
        "fixture_id": fixture_id,
        "category": fixture.get("category"),
        "passed": passed,
        "failures": failures,
        "elapsed_ms": elapsed,
    }
