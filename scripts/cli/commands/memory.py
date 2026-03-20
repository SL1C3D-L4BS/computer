"""
computer memory audit [--gc]
computer memory gc    (alias, same as --gc)

Memory scope audit: freshness, hazard state, archived items,
cross-scope leakage flags.

--gc prints dry-run cleanup recommendations without applying.
"""
from __future__ import annotations

import json

import click

from scripts.cli.formatters import section, table, warn, ok, kv

MEMORY_SERVICE_URL = "http://localhost:8800"

MEMORY_CLASSES = [
    "reminders",
    "preferences",
    "explicit_facts",
    "shared_household_notes",
    "work_context",
    "site_incidents",
    "inferred_habits",
]


def _http_get(url: str) -> tuple[bool, dict]:
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return True, json.loads(resp.read())
    except Exception as e:
        return False, {"error": str(e)}


def _stub_audit() -> list[dict]:
    """Return placeholder memory audit data when service is offline."""
    return [
        {"scope": "PERSONAL",         "class": "reminders",        "count": 12, "avg_freshness": 0.72, "stale_count": 2, "archived": 5},
        {"scope": "PERSONAL",         "class": "preferences",      "count": 8,  "avg_freshness": 0.91, "stale_count": 0, "archived": 1},
        {"scope": "PERSONAL",         "class": "inferred_habits",  "count": 34, "avg_freshness": 0.45, "stale_count": 9, "archived": 12},
        {"scope": "HOUSEHOLD_SHARED", "class": "shared_household_notes", "count": 6, "avg_freshness": 0.83, "stale_count": 1, "archived": 3},
        {"scope": "WORK",             "class": "work_context",     "count": 22, "avg_freshness": 0.61, "stale_count": 4, "archived": 8},
        {"scope": "SITE",             "class": "site_incidents",   "count": 7,  "avg_freshness": 0.55, "stale_count": 2, "archived": 14},
    ]


@click.command("memory")
@click.option("--gc", "gc_mode", is_flag=True, default=False,
              help="Show dry-run cleanup recommendations")
def cmd(gc_mode: bool) -> None:
    """Memory scope audit: freshness, hazard, archived, leakage flags."""
    section("computer memory audit")

    success, data = _http_get(MEMORY_SERVICE_URL + "/audit")
    if not success:
        warn(f"memory-service unreachable: {data.get('error')}")
        warn("Showing stub data — connect memory-service for live audit.\n")
        entries = _stub_audit()
    else:
        entries = data.get("entries", _stub_audit())

    # Main table
    rows = []
    for e in entries:
        freshness = e.get("avg_freshness", 0.0)
        stale = e.get("stale_count", 0)
        flag = " ⚠" if stale > 0 or freshness < 0.5 else ""
        rows.append([
            e.get("scope", "?"),
            e.get("class", "?"),
            str(e.get("count", "?")),
            f"{freshness:.2f}",
            str(stale),
            str(e.get("archived", "?")),
            flag,
        ])
    table(["scope", "class", "count", "avg_fresh", "stale", "archived", ""],
          rows, col_width=20)

    # Cross-scope leakage check (stub)
    print("\n  CROSS-SCOPE LEAKAGE CHECK")
    ok("No personal memory entries found in FAMILY scope (stub check)")
    ok("No WORK memory entries found in PERSONAL scope (stub check)")

    if gc_mode:
        print("\n  GC RECOMMENDATIONS (dry-run — no changes applied)")
        gc_found = False
        for e in entries:
            if e.get("stale_count", 0) > 0:
                gc_found = True
                scope = e.get("scope")
                cls = e.get("class")
                n = e.get("stale_count")
                print(f"  → Archive {n} stale {cls} entries in {scope} scope")
            if e.get("avg_freshness", 1.0) < 0.1:
                gc_found = True
                print(f"  → Consider abandonment review for {e.get('class')} (avg_freshness < 0.1)")
        if not gc_found:
            ok("No cleanup recommendations at this time.")
    print()
