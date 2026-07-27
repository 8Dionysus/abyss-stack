# AoA 4PDA Connector MCP Boundaries

- `aoa-4pda-connector` owns source-specific connector truth: policy, CLI,
  schemas, storage contract, parser, normalizer, indexes, graph, answer
  packets, readiness, and eval routes.
- `abyss-stack` owns this runnable MCP package, portable stdio and optional
  exact-owner authenticated loopback HTTP routes, stack validation, and
  deployment posture.
- The MCP package reads local connector JSON packets and does not author 4PDA
  facts or proof claims.
- Answer packets must preserve `agent_answer`, `evidence_chain`,
  `nuance_report`, `answer_report`, and `network_touched=false`.
- Heavy generated data belongs in configured connector storage roots, not Git.
- The first slice has no write, crawl, refresh-build, reindex, or network route.
- The managed read unit has no persistent writable path and denies
  non-loopback IP traffic.
