"""
Tool Registry — the catalog of registered MCP tools.

Every tool must declare:
- trust_tier (T0-T4)
- domain
- surfaces it's available on
- output_schema (MCP 2025 structuredContent format)

Drone arming is never registered. (ADR-002, ADR-005)
Control actuation is never registered. Use orchestrator (step 7b) for that.
"""
from __future__ import annotations

from mcp_gateway.policy import ToolDescriptor, TrustTier

TOOL_REGISTRY: dict[str, ToolDescriptor] = {

    # ── T0: Public informational ──────────────────────────────────────────────

    "time.current": ToolDescriptor(
        name="time.current",
        title="Current Time",
        description="Returns the current date and time in the system timezone",
        trust_tier=TrustTier.T0,
        domain="personal",
        surfaces=["*"],
        output_schema={
            "type": "object",
            "properties": {
                "iso8601": {"type": "string"},
                "timezone": {"type": "string"},
                "unix_epoch": {"type": "integer"},
            },
            "required": ["iso8601", "timezone"],
        },
    ),

    "weather.current": ToolDescriptor(
        name="weather.current",
        title="Current Weather",
        description="Returns current weather for the homestead site",
        trust_tier=TrustTier.T0,
        domain="personal",
        surfaces=["*"],
        output_schema={
            "type": "object",
            "properties": {
                "temperature_c": {"type": "number"},
                "humidity_pct": {"type": "number"},
                "conditions": {"type": "string"},
            },
        },
    ),

    # ── T1: Household informational ───────────────────────────────────────────

    "calendar.events": ToolDescriptor(
        name="calendar.events",
        title="Household Calendar",
        description="Returns upcoming household calendar events",
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "CHAT", "WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "start_iso8601": {"type": "string"},
                            "duration_minutes": {"type": "integer"},
                        },
                    },
                },
            },
        },
    ),

    "greenhouse.status": ToolDescriptor(
        name="greenhouse.status",
        title="Greenhouse Status",
        description="Returns current greenhouse sensor readings (read-only)",
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "CHAT", "WEB", "MOBILE", "OPS"],
        output_schema={
            "type": "object",
            "properties": {
                "temperature_c": {"type": "number"},
                "humidity_pct": {"type": "number"},
                "co2_ppm": {"type": "number"},
                "zones": {"type": "array", "items": {"type": "object"}},
            },
        },
    ),

    # ── T2: Personal sensitive ────────────────────────────────────────────────

    "memory.read": ToolDescriptor(
        name="memory.read",
        title="Personal Memory Read",
        description="Reads personal memory entries within the user's PERSONAL scope",
        trust_tier=TrustTier.T2,
        domain="personal",
        surfaces=["VOICE", "CHAT", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "entries": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "created_at": {"type": "string"},
                            "scope": {"type": "string"},
                        },
                    },
                },
            },
        },
    ),

    # ── T3: Site read-only ────────────────────────────────────────────────────

    "site.jobs.list": ToolDescriptor(
        name="site.jobs.list",
        title="Site Job List",
        description="Lists current and recent orchestrator jobs (read-only)",
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "jobs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "type": {"type": "string"},
                            "status": {"type": "string"},
                            "risk_class": {"type": "string"},
                        },
                    },
                },
            },
        },
    ),

    "site.sensors.read": ToolDescriptor(
        name="site.sensors.read",
        title="Site Sensor Data",
        description="Returns current MQTT sensor readings across the site",
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "sensors": {"type": "array", "items": {"type": "object"}},
                "timestamp": {"type": "string"},
            },
        },
    ),

    # ── T4: Site operational (adjacent to control; never direct actuation) ────

    "site.config.read": ToolDescriptor(
        name="site.config.read",
        title="Site Configuration Read",
        description="Returns site configuration (read-only; never modifies state)",
        trust_tier=TrustTier.T4,
        domain="site",
        surfaces=["OPS"],
        output_schema={
            "type": "object",
            "properties": {
                "config": {"type": "object"},
                "version": {"type": "string"},
            },
        },
    ),

    # ── T2: Founder Mode Decision-Support Tools (V3) ─────────────────────────
    # Trust tier: T2 (operator-level; requires identity_confidence > 0.85 in WORK mode)
    # Reference: docs/product/founder-operating-mode.md
    # All outputs include DecisionRationale and ConfidenceScore for audit logging.

    "briefing.daily": ToolDescriptor(
        name="briefing.daily",
        title="Daily Founder Briefing",
        description=(
            "Ranked decision agenda for the current session. "
            "Surfaces only items requiring a decision, ranked by deadline and cost of delay. "
            "Truncates to T1 items when unresolved_decision_load > 20."
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB", "VOICE"],
        output_schema={
            "type": "object",
            "required": ["briefing_date", "decision_load", "action_required", "metrics", "decision_rationale"],
            "properties": {
                "briefing_date": {"type": "string", "description": "ISO 8601 date of briefing"},
                "decision_load": {
                    "type": "object",
                    "properties": {
                        "t1_count": {"type": "integer"},
                        "t2_count": {"type": "integer"},
                        "total": {"type": "integer"},
                        "overloaded": {"type": "boolean"},
                    },
                },
                "action_required": {
                    "type": "array",
                    "description": "T1 items: decisions required today",
                    "items": {
                        "type": "object",
                        "required": ["id", "description", "urgency"],
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "deadline": {"type": "string"},
                            "urgency": {"type": "number", "minimum": 0, "maximum": 1},
                            "effective_priority": {"type": "number", "minimum": 0, "maximum": 1},
                            "context": {"type": "string"},
                        },
                    },
                },
                "stale_decisions": {
                    "type": "array",
                    "description": "T2 items: stale loops needing closure decision",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "age_hours": {"type": "number"},
                            "freshness": {"type": "number"},
                        },
                    },
                },
                "monitoring": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"id": {"type": "string"}, "summary": {"type": "string"}}},
                },
                "metrics": {
                    "type": "object",
                    "required": ["open_loops", "pending_commitments", "backlog_burn_down_rate"],
                    "properties": {
                        "open_loops": {"type": "integer"},
                        "pending_commitments": {"type": "integer"},
                        "decisions_resolved_last_7d": {"type": "integer"},
                        "backlog_burn_down_rate": {"type": "number"},
                        "mean_decision_age_hours": {"type": "number"},
                    },
                },
                "decision_rationale": {
                    "type": "object",
                    "description": "DecisionRationale for this briefing composition",
                },
            },
        },
    ),

    "decisions.register": ToolDescriptor(
        name="decisions.register",
        title="Register Decision",
        description=(
            "Append a founder decision to the permanent decision register. "
            "All three required fields (decision, context, rationale) must be non-empty. "
            "Returns decision record ID for future reference."
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB", "VOICE"],
        output_schema={
            "type": "object",
            "required": ["decision_id", "recorded_at", "decision", "confirmation", "decision_rationale"],
            "properties": {
                "decision_id": {"type": "string"},
                "recorded_at": {"type": "string"},
                "decision": {"type": "string"},
                "context": {"type": "string"},
                "rationale": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "alternatives": {"type": "array", "items": {"type": "string"}},
                "confirmation": {"type": "string", "enum": ["recorded"]},
                "review_scheduled_at": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "ISO 8601 timestamps for 7d, 30d, 90d retrospective reviews",
                },
                "decision_rationale": {
                    "type": "object",
                    "description": "DecisionRationale for this registration",
                },
            },
        },
    ),

    "context.load_repo": ToolDescriptor(
        name="context.load_repo",
        title="Load Repository Context",
        description=(
            "Loads current codebase/workstream context into working memory scope. "
            "Enables technical decisions without cold-start context cost. "
            "Context expires after 60 minutes."
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "required": ["context_id", "scope", "loaded_at", "items_loaded", "summary", "expiry_at", "decision_rationale"],
            "properties": {
                "context_id": {"type": "string"},
                "scope": {"type": "string"},
                "loaded_at": {"type": "string"},
                "items_loaded": {"type": "integer"},
                "summary": {"type": "string"},
                "expiry_at": {"type": "string"},
                "confidence": {
                    "type": "object",
                    "description": "ConfidenceScore for context relevance",
                    "properties": {
                        "value": {"type": "number"},
                        "type": {"type": "string"},
                        "source": {"type": "string"},
                    },
                },
                "decision_rationale": {
                    "type": "object",
                    "description": "DecisionRationale for this context load",
                },
            },
        },
    ),

    "loops.open_for_founder": ToolDescriptor(
        name="loops.open_for_founder",
        title="Open Loops for Founder",
        description=(
            "Returns ACTIVE open loops ranked by effective priority (priority_score × freshness). "
            "Highlights abandonment candidates. Optimized for founder decision throughput."
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB", "VOICE"],
        output_schema={
            "type": "object",
            "required": ["loops", "total_active", "abandonment_candidates", "decision_rationale"],
            "properties": {
                "loops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["id", "description", "effective_priority"],
                        "properties": {
                            "id": {"type": "string"},
                            "description": {"type": "string"},
                            "effective_priority": {"type": "number", "minimum": 0, "maximum": 1},
                            "freshness": {"type": "number", "minimum": 0, "maximum": 1},
                            "age_hours": {"type": "number"},
                            "owner_confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "resurfacing_recommendation": {"type": "string"},
                            "is_abandonment_candidate": {"type": "boolean"},
                        },
                    },
                },
                "total_active": {"type": "integer"},
                "abandonment_candidates": {"type": "integer"},
                "burn_down_rate": {"type": "number"},
                "decision_rationale": {
                    "type": "object",
                    "description": "DecisionRationale for this query",
                },
            },
        },
    ),

    # ── V4: Founder Extended (T2, WORK mode only) ─────────────────────────────
    # 7 new tools. Each: primary_mode=WORK, trust_tier=T2, failure_mode documented.
    # Audit payload example in docstring. Eval fixture: packages/eval-fixtures/

    "briefing.evening": ToolDescriptor(
        name="briefing.evening",
        title="Evening Founder Review",
        description=(
            "End-of-day decision review: loops closed today, outstanding items carried forward, "
            "decision velocity vs target. "
            "primary_mode=WORK | trust_tier=T2 | "
            "failure_mode=returns empty briefing with error field when no audit data is available. "
            "eval_fixture=founder_evening_briefing | "
            "audit_payload={'tool':'briefing.evening','decision':'INTERRUPT',"
            "'confidence':0.88,'cost':{'attention_units':1.0}}"
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "loops_closed_today": {"type": "integer"},
                "carried_forward": {"type": "array", "items": {"type": "object"}},
                "velocity": {"type": "number"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "decisions.diff": ToolDescriptor(
        name="decisions.diff",
        title="Decision Register Diff",
        description=(
            "Returns decisions made in the last N days vs prior period. "
            "Surfaces velocity change and recency of high-stakes decisions. "
            "primary_mode=WORK | trust_tier=T2 | "
            "failure_mode=returns empty diff when no decisions recorded. "
            "eval_fixture=founder_decisions_diff | "
            "audit_payload={'tool':'decisions.diff','decision':'DIGEST',"
            "'confidence':0.91,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "period_days": {"type": "integer"},
                "decisions_this_period": {"type": "array", "items": {"type": "object"}},
                "velocity_change": {"type": "number"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "releases.watch": ToolDescriptor(
        name="releases.watch",
        title="Release Watch",
        description=(
            "Lists active release trains, their current status, and any blocking issues. "
            "primary_mode=WORK | trust_tier=T2 | "
            "failure_mode=returns empty list when CI/CD pipeline is unreachable. "
            "eval_fixture=founder_releases_watch | "
            "audit_payload={'tool':'releases.watch','decision':'DIGEST',"
            "'confidence':0.85,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "trains": {"type": "array", "items": {"type": "object"}},
                "blocked_count": {"type": "integer"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "incidents.digest": ToolDescriptor(
        name="incidents.digest",
        title="Incident Digest",
        description=(
            "Returns open incidents, severity distribution, and MTTR trend. "
            "primary_mode=WORK | trust_tier=T2 | "
            "failure_mode=returns empty digest with error when incident tracker is unreachable. "
            "eval_fixture=founder_incidents_digest | "
            "audit_payload={'tool':'incidents.digest','decision':'INTERRUPT',"
            "'confidence':0.93,'cost':{'attention_units':2.0}}"
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB", "VOICE"],
        output_schema={
            "type": "object",
            "properties": {
                "open_incidents": {"type": "array", "items": {"type": "object"}},
                "severity_counts": {"type": "object"},
                "mttr_trend": {"type": "number"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "repos.status": ToolDescriptor(
        name="repos.status",
        title="Repository Status",
        description=(
            "Returns branch health, open PR count, and failing CI checks across repositories. "
            "primary_mode=WORK | trust_tier=T2 | "
            "failure_mode=returns partial data with unreachable_repos list when VCS is degraded. "
            "eval_fixture=founder_repos_status | "
            "audit_payload={'tool':'repos.status','decision':'DIGEST',"
            "'confidence':0.87,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "repos": {"type": "array", "items": {"type": "object"}},
                "failing_ci_count": {"type": "integer"},
                "unreachable_repos": {"type": "array", "items": {"type": "string"}},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "docs.search_local": ToolDescriptor(
        name="docs.search_local",
        title="Local Documentation Search",
        description=(
            "Full-text search across docs/architecture/, docs/product/, docs/safety/. "
            "Returns matching file paths and excerpt. "
            "primary_mode=WORK | trust_tier=T2 | "
            "failure_mode=returns empty results with error when docs index is unavailable. "
            "eval_fixture=founder_docs_search | "
            "audit_payload={'tool':'docs.search_local','decision':'DIGEST',"
            "'confidence':0.82,'cost':{'attention_units':0.3}}"
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "results": {"type": "array", "items": {"type": "object"}},
                "query": {"type": "string"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "loops.resolve": ToolDescriptor(
        name="loops.resolve",
        title="Resolve Open Loop",
        description=(
            "Marks a named open loop as CLOSED or ABANDONED with a resolution note. "
            "Triggers FollowUpWorkflow signal if the loop has a linked workflow. "
            "primary_mode=WORK | trust_tier=T2 | "
            "failure_mode=returns error with loop_id when loop not found or already closed. "
            "eval_fixture=founder_loops_resolve | "
            "audit_payload={'tool':'loops.resolve','decision':'INTERRUPT',"
            "'confidence':0.96,'cost':{'attention_units':1.5}}"
        ),
        trust_tier=TrustTier.T2,
        domain="founder",
        surfaces=["OPS", "WEB", "VOICE"],
        output_schema={
            "type": "object",
            "properties": {
                "loop_id": {"type": "string"},
                "resolution": {"type": "string"},
                "status": {"type": "string", "enum": ["CLOSED", "ABANDONED"]},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    # ── V4: Family/Household (T1, FAMILY+PERSONAL modes) ──────────────────────
    # 8 new tools. Each: primary_mode=FAMILY, trust_tier=T1, failure_mode documented.

    "shopping.plan_week": ToolDescriptor(
        name="shopping.plan_week",
        title="Weekly Shopping Plan",
        description=(
            "Generates a weekly shopping list from household preferences and pantry state. "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns partial list with missing_data field when pantry state unavailable. "
            "eval_fixture=family_shopping_plan | "
            "audit_payload={'tool':'shopping.plan_week','decision':'DIGEST',"
            "'confidence':0.79,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "CHAT", "WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object"}},
                "missing_data": {"type": "array", "items": {"type": "string"}},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "chores.balance_load": ToolDescriptor(
        name="chores.balance_load",
        title="Chore Load Balancer",
        description=(
            "Redistributes household chore assignments based on availability and history. "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns current assignments unchanged with error when member data missing. "
            "eval_fixture=family_chores_balance | "
            "audit_payload={'tool':'chores.balance_load','decision':'DIGEST',"
            "'confidence':0.81,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "assignments": {"type": "array", "items": {"type": "object"}},
                "balance_score": {"type": "number"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "calendar.household_conflicts": ToolDescriptor(
        name="calendar.household_conflicts",
        title="Household Calendar Conflicts",
        description=(
            "Detects scheduling conflicts across all household members for the next N days. "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns empty conflicts list when calendar service is unreachable. "
            "eval_fixture=family_calendar_conflicts | "
            "audit_payload={'tool':'calendar.household_conflicts','decision':'DIGEST',"
            "'confidence':0.88,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "conflicts": {"type": "array", "items": {"type": "object"}},
                "days_ahead": {"type": "integer"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "approvals.pending": ToolDescriptor(
        name="approvals.pending",
        title="Pending Family Approvals",
        description=(
            "Lists pending household approval requests (purchases, schedule changes, guests). "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns empty list with error when approval service is unavailable. "
            "eval_fixture=family_approvals_pending | "
            "audit_payload={'tool':'approvals.pending','decision':'INTERRUPT',"
            "'confidence':0.90,'cost':{'attention_units':1.0}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "pending": {"type": "array", "items": {"type": "object"}},
                "overdue_count": {"type": "integer"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "home.status_digest": ToolDescriptor(
        name="home.status_digest",
        title="Home Status Digest",
        description=(
            "Summary of active household appliances, energy usage, and any alerts. "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns partial digest with unavailable_systems list when HA is degraded. "
            "eval_fixture=family_home_status | "
            "audit_payload={'tool':'home.status_digest','decision':'DIGEST',"
            "'confidence':0.84,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "alerts": {"type": "array", "items": {"type": "object"}},
                "energy_kwh_today": {"type": "number"},
                "unavailable_systems": {"type": "array", "items": {"type": "string"}},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "memory.share_explicit": ToolDescriptor(
        name="memory.share_explicit",
        title="Explicit Memory Share",
        description=(
            "Shares a specific personal memory entry to HOUSEHOLD_SHARED scope "
            "with explicit user consent captured. Requires approval_track auth. "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns denied with reason when consent not captured or I-02 violated. "
            "eval_fixture=family_memory_share | "
            "audit_payload={'tool':'memory.share_explicit','decision':'INTERRUPT',"
            "'confidence':0.95,'cost':{'attention_units':2.0}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "shared_entry_id": {"type": "string"},
                "status": {"type": "string"},
                "consent_recorded_at": {"type": "string"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "guest.safe_answer": ToolDescriptor(
        name="guest.safe_answer",
        title="Guest Safe Answer",
        description=(
            "Returns a privacy-safe answer for a question from a household guest "
            "(non-resident). Never returns personal memory or private household data. "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns generic deflection response when intent unclear. "
            "eval_fixture=family_guest_safe_answer | "
            "audit_payload={'tool':'guest.safe_answer','decision':'DIGEST',"
            "'confidence':0.97,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "privacy_scope": {"type": "string"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "followup.family_open_loops": ToolDescriptor(
        name="followup.family_open_loops",
        title="Family Open Loops",
        description=(
            "Lists open follow-up items in FAMILY scope: unresolved commitments, "
            "unanswered questions, pending shared tasks. "
            "primary_mode=FAMILY | trust_tier=T1 | "
            "failure_mode=returns empty list with error when loop store is unavailable. "
            "eval_fixture=family_followup_loops | "
            "audit_payload={'tool':'followup.family_open_loops','decision':'DIGEST',"
            "'confidence':0.83,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T1,
        domain="household",
        surfaces=["VOICE", "WEB", "MOBILE"],
        output_schema={
            "type": "object",
            "properties": {
                "loops": {"type": "array", "items": {"type": "object"}},
                "overdue_count": {"type": "integer"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    # ── V4: Site/Ops (T3, WORK+SITE modes) ────────────────────────────────────
    # 6 new tools. Each: primary_mode=SITE, trust_tier=T3, failure_mode documented.

    "site.read_snapshot": ToolDescriptor(
        name="site.read_snapshot",
        title="Site State Snapshot",
        description=(
            "Returns a point-in-time snapshot of all site subsystem states. Read-only. "
            "primary_mode=SITE | trust_tier=T3 | "
            "failure_mode=returns partial snapshot with degraded_subsystems list. "
            "eval_fixture=site_read_snapshot | "
            "audit_payload={'tool':'site.read_snapshot','decision':'DIGEST',"
            "'confidence':0.92,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "snapshot_at": {"type": "string"},
                "subsystems": {"type": "object"},
                "degraded_subsystems": {"type": "array", "items": {"type": "string"}},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "jobs.pending_risk": ToolDescriptor(
        name="jobs.pending_risk",
        title="Pending Jobs Risk Assessment",
        description=(
            "Lists pending orchestrator jobs with risk_class >= MEDIUM and estimated impact. "
            "primary_mode=SITE | trust_tier=T3 | "
            "failure_mode=returns empty list when orchestrator is unreachable. "
            "eval_fixture=site_jobs_pending_risk | "
            "audit_payload={'tool':'jobs.pending_risk','decision':'INTERRUPT',"
            "'confidence':0.89,'cost':{'attention_units':2.0}}"
        ),
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "jobs": {"type": "array", "items": {"type": "object"}},
                "highest_risk": {"type": "string"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "greenhouse.explain_drift": ToolDescriptor(
        name="greenhouse.explain_drift",
        title="Greenhouse Drift Explanation",
        description=(
            "Explains detected drift in greenhouse sensor readings vs expected baseline. "
            "primary_mode=SITE | trust_tier=T3 | "
            "failure_mode=returns no_drift_detected when baseline is unavailable. "
            "eval_fixture=site_greenhouse_drift | "
            "audit_payload={'tool':'greenhouse.explain_drift','decision':'DIGEST',"
            "'confidence':0.76,'cost':{'attention_units':1.0}}"
        ),
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB", "VOICE"],
        output_schema={
            "type": "object",
            "properties": {
                "drifting_sensors": {"type": "array", "items": {"type": "object"}},
                "explanation": {"type": "string"},
                "recommended_action": {"type": "string"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "energy.peak_window_plan": ToolDescriptor(
        name="energy.peak_window_plan",
        title="Energy Peak Window Plan",
        description=(
            "Returns recommended load-shifting plan for upcoming peak energy windows. "
            "primary_mode=SITE | trust_tier=T3 | "
            "failure_mode=returns empty plan when energy pricing data is unavailable. "
            "eval_fixture=site_energy_peak_window | "
            "audit_payload={'tool':'energy.peak_window_plan','decision':'DIGEST',"
            "'confidence':0.80,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "peak_windows": {"type": "array", "items": {"type": "object"}},
                "shift_recommendations": {"type": "array", "items": {"type": "object"}},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "security.incident_timeline": ToolDescriptor(
        name="security.incident_timeline",
        title="Security Incident Timeline",
        description=(
            "Returns a chronological timeline of recent security events and access anomalies. "
            "primary_mode=SITE | trust_tier=T3 | "
            "failure_mode=returns partial timeline with missing_period field when logs are incomplete. "
            "eval_fixture=site_security_timeline | "
            "audit_payload={'tool':'security.incident_timeline','decision':'INTERRUPT',"
            "'confidence':0.94,'cost':{'attention_units':2.0}}"
        ),
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "events": {"type": "array", "items": {"type": "object"}},
                "anomaly_count": {"type": "integer"},
                "missing_period": {"type": "string"},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    "sensors.confidence_report": ToolDescriptor(
        name="sensors.confidence_report",
        title="Sensor Confidence Report",
        description=(
            "Returns calibration confidence scores for all site sensors. "
            "Flags sensors with confidence below threshold for maintenance. "
            "primary_mode=SITE | trust_tier=T3 | "
            "failure_mode=returns empty report when sensor service is unreachable. "
            "eval_fixture=site_sensor_confidence | "
            "audit_payload={'tool':'sensors.confidence_report','decision':'DIGEST',"
            "'confidence':0.88,'cost':{'attention_units':0.5}}"
        ),
        trust_tier=TrustTier.T3,
        domain="site",
        surfaces=["OPS", "WEB"],
        output_schema={
            "type": "object",
            "properties": {
                "sensors": {"type": "array", "items": {"type": "object"}},
                "below_threshold": {"type": "array", "items": {"type": "string"}},
                "decision_rationale": {"type": "object"},
            },
        },
    ),

    # NOTE: No "drone.arm", no "valve.open", no "heater.enable" here.
    # Those are orchestrator jobs submitted via step 7b.
    # ADR-002, ADR-005: AI may never directly actuate hardware.
}


def get_tool(name: str) -> ToolDescriptor | None:
    return TOOL_REGISTRY.get(name)


def list_tools(
    domain: str | None = None,
    surface: str | None = None,
    mode: str | None = None,
) -> list[ToolDescriptor]:
    """Return filtered tool list. Tools filtered by domain, surface, and mode."""
    tools = list(TOOL_REGISTRY.values())

    if domain:
        tools = [t for t in tools if t.domain == domain]

    if surface:
        tools = [t for t in tools if "*" in t.surfaces or surface in t.surfaces]

    # Mode filtering: suppress site-adjacent tools in non-site modes
    # Founder tools (domain="founder") are available in WORK mode only
    if mode:
        _mode_tier_map = {
            "PERSONAL":  ["T0", "T1", "T2"],
            "FAMILY":    ["T0", "T1"],
            "WORK":      ["T0", "T1", "T2", "T3", "T4"],
            "SITE":      ["T0", "T1", "T2", "T3", "T4"],
            "EMERGENCY": ["T0"],
        }
        allowed_tiers = _mode_tier_map.get(mode, ["T0"])
        filtered = []
        for t in tools:
            if t.domain == "founder":
                # Founder tools only available in WORK mode
                if mode == "WORK":
                    filtered.append(t)
            elif t.trust_tier.value in allowed_tiers:
                filtered.append(t)
        tools = filtered

    return tools
