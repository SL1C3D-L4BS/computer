"""
computer auth check <subject> <action> <resource>

Dry-run auth check against authz-service /authorize.
Prints relation/scope path and decision.
"""
from __future__ import annotations

import json

import click

from scripts.cli.formatters import section, kv, warn, ok, err

AUTHZ_SERVICE_URL = "http://localhost:8300"


def _authorize(subject: str, action: str, resource: str,
               mode: str = "PERSONAL", risk_class: str = "LOW") -> dict:
    import urllib.request
    payload = {
        "subject": subject,
        "resource": resource,
        "action": action,
        "context": {
            "mode": mode,
            "risk_class": risk_class,
            "origin": "OPERATOR",
            "location": None,
            "time_of_day": None,
        },
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        AUTHZ_SERVICE_URL + "/authorize",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e), "allowed": None}


@click.command("auth")
@click.argument("subject")
@click.argument("action")
@click.argument("resource")
@click.option("--mode", default="PERSONAL", help="Mode context (PERSONAL/FAMILY/WORK/SITE/EMERGENCY)")
@click.option("--risk", default="LOW", help="Risk class (LOW/MEDIUM/HIGH/CRITICAL)")
def cmd(subject: str, action: str, resource: str, mode: str, risk: str) -> None:
    """Dry-run auth check: computer auth check <subject> <action> <resource>."""
    section(f"computer auth check")

    kv("subject",    subject)
    kv("action",     action)
    kv("resource",   resource)
    kv("mode",       mode)
    kv("risk_class", risk)
    print()

    result = _authorize(subject, action, resource, mode, risk)

    if "error" in result and result.get("allowed") is None:
        warn(f"authz-service unreachable: {result['error']}")
        warn("Cannot perform live auth check without authz-service running.")
        _stub_check(subject, action, resource, mode, risk)
        return

    allowed = result.get("allowed", False)
    reason = result.get("reason", "")
    policy = result.get("applicable_policy", "")

    if allowed:
        ok(f"ALLOWED  — {reason}")
    else:
        err(f"DENIED   — {reason}")

    if policy:
        kv("  applicable_policy", policy)
    print()


def _stub_check(subject: str, action: str, resource: str, mode: str, risk: str) -> None:
    """Fallback static logic for offline inspection."""
    print("  [stub] Applying static RBAC rules:")
    if risk in ("HIGH", "CRITICAL") and mode not in ("WORK", "SITE"):
        err(f"DENIED (stub) — HIGH/CRITICAL risk requires WORK or SITE mode")
    elif action.startswith("site.") and mode not in ("WORK", "SITE"):
        err(f"DENIED (stub) — site actions require WORK or SITE mode")
    elif action.startswith("memory.") and mode == "FAMILY":
        err(f"DENIED (stub) — personal memory not accessible in FAMILY mode")
    else:
        ok(f"ALLOWED (stub) — no static rule blocks this")
    print()
