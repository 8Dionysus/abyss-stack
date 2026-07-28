# AGENTS.md

This stack-owned package filters the independently runnable owner MCP API from
`aoa-course-connector` into an OS read contour.

The owner keeps course/source/evidence semantics. The OS wrapper must exclude
`connected_run` and all live, plan, auth, browser, refresh, or fixture-execution
surfaces. It must force source refs off and never expose token or browser state.

Validate with:

```bash
python mcp/services/aoa-course-connector-mcp/scripts/validate_course_connector_mcp.py
python -m pytest mcp/services/aoa-course-connector-mcp/tests -q
```
