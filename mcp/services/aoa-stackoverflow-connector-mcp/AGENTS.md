# AGENTS.md

This package is the stack-owned read-only access plane over
`aoa-stackoverflow-connector` packets. The connector owns source policy and
meaning; this package owns only authenticated local MCP wrapping.

Never expose crawl/build/write/account/ask/answer/comment/edit/vote/delete or
internal-search routes. Validate with:

Require query and answer packets to prove `network_touched=false` and
`read_only=true`. Do not publish `query-hybrid` until that command exists in
the current owner CLI.

```bash
python mcp/services/aoa-stackoverflow-connector-mcp/scripts/validate_stackoverflow_connector_mcp.py
python -m pytest mcp/services/aoa-stackoverflow-connector-mcp/tests -q
```
