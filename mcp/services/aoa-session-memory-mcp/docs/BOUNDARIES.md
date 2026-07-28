# Boundaries

## Authority Split

| Context | Owns | Does not own |
| --- | --- | --- |
| `.aoa` | raw sessions, manifests, segment indexes, route-signal classifier, search index, atlas maps, diagnostics, retrieval packets | MCP packaging |
| generated `.aoa` companions | deterministic route/search/readiness read models | reviewed truth stronger than raw evidence |
| `aoa-session-memory-mcp` | read-only access, compact route/evidence packets, freshness checks, prompts, CLI, service-local validation | archive mutation, reindexing, repair, distillation, naming, promotion, writeback, durable memory |
| `abyss-stack` | runnable MCP package and local transport topology | `.aoa` archive meaning or session evidence authority |
| `aoa-memo` | durable reviewed memory and writeback review | raw session archive truth |

## Interface

`aoa-session-memory-mcp` calls fixed `.aoa` read commands and reads fixed
generated JSON surfaces under the configured `.aoa` root.

It returns compact JSON objects with route candidates, session refs, segment
refs, raw refs, route signals, freshness status, diagnostics summaries, and
explicit authority boundaries. Typed skill packets may also carry
producer-owned candidate states, action summaries, and accepted-versus-rejected
correlation discriminators; MCP transports those fields but does not promote
them into invocation, effectiveness, or proof verdicts.

Route hits are candidate evidence. Search results, atlas entries, diagnostics,
and MCP responses are not reviewed truth.

## Stop Lines

- No archive write tools.
- No `index-maintenance --apply`.
- No reindex, relabel, repair, distillation, naming, export, install, hook, or
  promotion commands.
- No durable memory writeback.
- No proof verdict computation.
- No raw transcript bulk exposure by default.
- No treating MCP output as stronger than `.aoa` raw refs or reviewed owner
  sources.
- No remote, wildcard-bind, gateway, or proxy exposure; optional shared HTTP
  remains authenticated and loopback-only under `ABYSS-STACK-D-0077`.
- No shared owner credential: the read contour accepts only the
  `aoa-session-memory` bearer, scope, and client identity.
- No read-write SQLite connection in an MCP fast path; generated databases are
  opened with `mode=ro` and `query_only`.
