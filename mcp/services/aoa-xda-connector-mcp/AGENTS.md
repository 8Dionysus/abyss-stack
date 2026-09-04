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

Use the on-demand validation route in `VALIDATION.md` for the exact focused procedure.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.
