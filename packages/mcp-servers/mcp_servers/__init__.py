"""
MCP Server Stubs

Internal MCP server definitions. Each server exposes tools on a specific domain.

Servers:
- repo: GitHub / repo tools (commit, PR, issue status)
- family: Household calendar, shopping, shared notes
- site-readonly: Site sensors, job status (T3 read-only)
- ops-guarded: Site configuration with T4 operator-only access

None of these servers expose direct hardware actuation (step 7b only).
"""
