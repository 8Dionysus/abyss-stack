# AGENTS.md

This package is the stack-owned read-only access plane over
`aoa-stackoverflow-connector` packets. The connector owns source policy and
meaning; this package owns only authenticated local MCP wrapping.

Never expose crawl/build/write/account/ask/answer/comment/edit/vote/delete or
internal-search routes. Validate with:

Require query and answer packets to prove `network_touched=false` and
`read_only=true`. Do not publish `query-hybrid` until that command exists in
the current owner CLI.

Validation is on-demand: use [VALIDATION.md](../../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.
