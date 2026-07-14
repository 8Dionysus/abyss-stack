# AoA 4PDA Connector MCP Threat Model

## Protected Boundary

The protected boundary is the distinction between source-owned 4PDA connector
truth and stack-owned MCP access behavior.

## Main Risks

- Treating MCP packets as stronger than connector answer packets, receipts, or
  source URLs.
- Accidentally exposing crawl, refresh-build, reindex, or write behavior as an
  agent tool.
- Letting answer/query tools touch the network or call 4PDA internal search.
- Losing `agent_answer`, `evidence_chain`, `nuance_report`, `answer_report`, or
  `network_touched=false` while wrapping answers.
- Committing generated corpora, indexes, vectors, graphs, receipts, sqlite,
  parquet, qdrant, lancedb, or caches into `abyss-stack`.
- Letting anonymous local HTTP callers query connector-derived evidence.

## Mitigations

- The core wrapper has explicit read-only methods and no generic command tool.
- Commands are executed as argv lists without a shell.
- Query, run id, and limit inputs are bounded.
- Tests use a fake command runner and assert answer packet preservation.
- The validator checks package files, read-only source-route posture, server
  build, and a fake Xiaomi 13T answer packet.
- Optional loopback HTTP requires the source-owned bearer credential before
  MCP dispatch; stdio remains the portable default.
