# Boundaries

- `aoa-discord-connector` owns Discord source policy, schemas, parser,
  normalizer, storage contract, graph/index builders, and answer semantics.
- `aoa-discord-connector-mcp` owns only MCP tool shape, resource shape, CLI
  wrapping, and boundary checks around connector JSON packets.
- abyss-stack owns local runtime packaging and service registration.
- Generated corpora, exports, indexes, graphs, receipts, caches, vectors, and
  account/session state are runtime artifacts and must stay out of this repo.
- MCP tools are read-only and must not initiate network collection or source
  mutation.
- The managed HTTP process receives only the Discord read credential and has
  no persistent write path or non-loopback network route.
