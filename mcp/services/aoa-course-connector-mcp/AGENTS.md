# AGENTS.md

This stack-owned package filters the independently runnable owner MCP API from
`aoa-course-connector` into an OS read contour.

The owner keeps course/source/evidence semantics. The OS wrapper must exclude
`connected_run` and all live, plan, auth, browser, refresh, or fixture-execution
surfaces. It must force source refs off and never expose token or browser state.

Validate with:

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.
