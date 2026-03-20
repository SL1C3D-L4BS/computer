"""
computer workflow list|inspect|resume|cancel|sweep

Durable workflow operations via workflow-runtime /workflows endpoint.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import click

from scripts.cli.formatters import section, table, warn, kv, ok, err

WORKFLOW_RUNTIME_URL = "http://localhost:8400"


def _http(method: str, path: str, body: dict | None = None) -> tuple[bool, dict]:
    import urllib.request
    url = WORKFLOW_RUNTIME_URL + path
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return True, json.loads(resp.read())
    except Exception as e:
        return False, {"error": str(e)}


@click.group("workflow")
def cmd() -> None:
    """Durable workflow operations (list, inspect, resume, cancel, sweep)."""


@cmd.command("list")
@click.option("--status", default=None, help="Filter by status (RUNNING, PAUSED, COMPLETED, FAILED)")
def wf_list(status: str | None) -> None:
    """List active durable workflows."""
    section("computer workflow list")
    success, data = _http("GET", "/workflows")
    if not success:
        warn(f"workflow-runtime unreachable: {data.get('error')}")
        _show_stub_list()
        return
    workflows = data.get("workflows", [])
    if status:
        workflows = [w for w in workflows if w.get("status", "").upper() == status.upper()]
    if not workflows:
        print("  No workflows found.\n")
        return
    rows = [[w.get("workflow_id", "?")[:36], w.get("type", "?"), w.get("status", "?"),
             w.get("created_at", "?")[:19]] for w in workflows]
    table(["workflow_id", "type", "status", "created_at"], rows, col_width=24)
    print()


def _show_stub_list() -> None:
    print("  (Stub) Canonical workflow classes:")
    for cls in ["ReminderWorkflow", "ApprovalWorkflow", "RoutineWorkflow", "FollowUpWorkflow"]:
        print(f"    • {cls}")
    print()


@cmd.command("inspect")
@click.argument("workflow_id")
def wf_inspect(workflow_id: str) -> None:
    """Inspect a specific workflow."""
    section(f"computer workflow inspect  {workflow_id}")
    success, data = _http("GET", f"/workflows/{workflow_id}")
    if not success:
        warn(f"workflow-runtime unreachable: {data.get('error')}")
        return
    for key in ("workflow_id", "type", "status", "created_at", "task_queue", "domain"):
        kv(key, data.get(key, "?"))
    signals = data.get("pending_signals", [])
    if signals:
        print(f"\n  Pending signals: {signals}")
    print()


@cmd.command("resume")
@click.argument("workflow_id")
def wf_resume(workflow_id: str) -> None:
    """Send a resume signal to a paused workflow."""
    section(f"computer workflow resume  {workflow_id}")
    success, data = _http("POST", f"/workflows/{workflow_id}/signal",
                          {"signal": "resume", "payload": {}})
    if success:
        ok(f"Resume signal sent to {workflow_id}")
    else:
        err(f"Failed: {data.get('error')}")
    print()


@cmd.command("cancel")
@click.argument("workflow_id")
@click.confirmation_option(prompt="Cancel this workflow?")
def wf_cancel(workflow_id: str) -> None:
    """Cancel a running workflow."""
    section(f"computer workflow cancel  {workflow_id}")
    success, data = _http("POST", f"/workflows/{workflow_id}/cancel", {})
    if success:
        ok(f"Workflow {workflow_id} cancelled")
    else:
        err(f"Failed: {data.get('error')}")
    print()


@cmd.command("sweep")
@click.option("--dry-run", is_flag=True, default=True, help="Show stale workflows without cancelling")
def wf_sweep(dry_run: bool) -> None:
    """Detect stale/orphaned workflows exceeding their sweep policy."""
    section("computer workflow sweep")
    success, data = _http("GET", "/workflows")
    if not success:
        warn(f"workflow-runtime unreachable: {data.get('error')}")
        warn("Sweep requires live workflow-runtime service.")
        return

    now = datetime.now(timezone.utc)
    stale = []
    STALE_THRESHOLDS = {
        "ReminderWorkflow": 90 * 24 * 3600,
        "ApprovalWorkflow": 7 * 24 * 3600,
        "RoutineWorkflow":  48 * 3600,
        "FollowUpWorkflow": 30 * 24 * 3600,
    }

    for wf in data.get("workflows", []):
        wf_type = wf.get("type", "")
        threshold = STALE_THRESHOLDS.get(wf_type, 30 * 24 * 3600)
        created = wf.get("created_at", "")
        if created:
            try:
                age = (now - datetime.fromisoformat(created.replace("Z", "+00:00"))).total_seconds()
                if age > threshold:
                    stale.append((wf.get("workflow_id", "?"), wf_type, f"{int(age/3600)}h old"))
            except Exception:
                pass

    if not stale:
        ok("No stale workflows detected.")
    else:
        print(f"\n  Found {len(stale)} stale workflow(s):\n")
        table(["workflow_id", "type", "age"], stale, col_width=26)
        if dry_run:
            print("\n  Dry run — pass --no-dry-run to cancel these workflows.\n")
        else:
            for wf_id, _, _ in stale:
                _http("POST", f"/workflows/{wf_id}/cancel", {})
            ok(f"Cancelled {len(stale)} stale workflow(s)")
    print()
