# AGENTS.md

This package is the stack-owned, read-only MCP access plane over
`aoa-xda-connector` owner packets.

- The connector owns source policy, schemas, graph/answer semantics, and data.
- This package owns authenticated local transport and thin packet preservation.
- Expose only status, source-route, graph query, and answer.
- Never expose crawl, build, write, login, private, reply, attachment, download,
  or internal-search routes.
- Require query and answer packets to prove `network_touched=false` and
  `read_only=true`; do not publish `query-hybrid` until the owner CLI has it.

Validate with:

```bash
python mcp/services/aoa-xda-connector-mcp/scripts/validate_xda_connector_mcp.py
python -m pytest mcp/services/aoa-xda-connector-mcp/tests -q
```
