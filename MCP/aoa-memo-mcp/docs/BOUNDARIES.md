# Boundaries

## Authority Split

| Context | Owns | Does not own |
|---|---|---|
| `aoa-memo` | reviewed memory truth and memory operation contracts | raw session archive or live host facts |
| `.aoa` | raw session evidence, compaction intervals, indexes, rehydration evidence | reviewed memory truth |
| local `memo/` ports | candidates, receipts, exports, local notes | central promotion |
| `aoa-memo-mcp` | access, search, brief, candidate helper, validation helper | authority to promote durable memory |

## Interface

Local ports send candidates forward through reviewed intake.
`aoa-memo-mcp` can create and validate a candidate, but the reviewed landing
belongs to `aoa-memo`.

Session resources expose rehydration pointers, not raw transcript replacement.
Agents may use them to find evidence and then inspect the owning archive.

## Pilot Port Layout

```text
memo/
  AGENTS.md
  README.md
  candidates/
  receipts/
  exports/
  local/
```

`candidates/` stores proposed memory objects or intake packets.
`receipts/` stores accept/reject/forward traces.
`exports/` stores handoff packets for `aoa-memo`.
`local/` stores repo-local notes that should not become central memory yet.
