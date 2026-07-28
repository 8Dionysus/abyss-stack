# Boundaries

## Authority Split

| Context | Owns | Does not own |
|---|---|---|
| `aoa-memo` | reviewed memory truth and memory operation contracts | raw session archive or live host facts |
| `.aoa` | raw session evidence, compaction intervals, indexes, rehydration evidence | reviewed memory truth |
| local `memo/` ports | candidates, receipts, exports, local notes | central promotion |
| `aoa-memo-mcp` read contour | access, search, brief, validation, pending-export inspection, non-writing plans | persistent local or durable memory mutation |
| `aoa-memo-mcp` candidate contour | allowlisted local candidate, generated-index, export, and forwarding-receipt writes | durable corpus mutation, acceptance, arbitrary local-port discovery-as-authority |

## Interface

Local ports send candidates forward through reviewed intake.
`aoa-memo-mcp` can create and validate a candidate, build or check the local
port index, prepare reviewed-intake exports, and write local forwarding-check
receipts.
The reviewed landing belongs to `aoa-memo`. Read and candidate tools never
share one MCP endpoint or bearer. The read process cannot enumerate persistent
tools and its systemd filesystem is read-only. The candidate process has a
finite application root allowlist plus exact systemd write paths; a newly
discovered port remains unwritable until those source-owned lists change.

Packet tools are confined to known local `memo/` ports. Candidate, export, and
receipt references are local packet refs, not arbitrary absolute paths, and
their shapes are checked against `aoa-memo/schemas/memory-ports/`.
The known-port set is derived from the `8Dionysus` workspace memory map when
available, with the original pilot ports kept only as bootstrap fallback.

Session resources expose rehydration pointers, not raw transcript replacement.
Agents may use them to find evidence and then inspect the owning archive.

## Pilot Port Layout

```text
memo/
  AGENTS.md
  README.md
  PORT.yaml
  INDEX.md
  index.min.json
  candidates/
  receipts/
  exports/
  local/
```

`candidates/` stores proposed memory objects or intake packets.
`receipts/` stores accept/reject/forward traces.
`exports/` stores handoff packets for `aoa-memo`.
`local/` stores repo-local notes that should not become central memory yet.
