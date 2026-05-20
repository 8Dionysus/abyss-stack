# aoa-memo-mcp

`aoa-memo-mcp` exposes OS Abyss memory through a small MCP access plane.

It does not replace `aoa-memo`, `.aoa`, or local `memo/` ports. It gives agents
one repeatable route to ask:

- what memory is relevant here;
- whether this place has a local memo port;
- how to create a candidate;
- how to validate that candidate before any durable memory landing;
- where session rehydration evidence lives.

## Source Hierarchy

| Layer | Role |
|---|---|
| `aoa-memo` | reviewed memory truth, contracts, lifecycle, guardrails, operation modes, consolidation, eval/KAG handoff |
| `.aoa` | raw session archive, compaction intervals, generated segment evidence, rehydration packets |
| `repo/memo/` | local candidates, receipts, exports, and repo-local memory notes |
| `aoa-memo-mcp` | live MCP access plane over those surfaces |

## MCP Surface

Resources:

- `aoa-memo://brief/repo/{repo}`
- `aoa-memo://memory/object/{id}`
- `aoa-memo://session/{session_id}/rehydrate`
- `aoa-memo://repo/{repo}/local-port-status`

Tools:

- `aoa_memo_brief(repo, intent)`
- `aoa_memo_search(query, scope, mode)`
- `aoa_memo_create_candidate(repo, evidence_refs, claim)`
- `aoa_memo_validate_candidate(path)`

Prompts:

- `memo-brief`
- `memo-intake`
- `memo-review`
- `session-rehydrate`

## Run

```bash
python mcp/services/aoa-memo-mcp/scripts/aoa_memo_mcp_server.py
```

In the shared AoA Codex plane this service is registered as `aoa_memo` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. The workspace launcher
is `<workspace-root>/.codex/bin/aoa-memo-mcp-server.py`; it resolves this
stack-owned service without making `8Dionysus` the service authority.

For direct smoke checks:

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli brief --repo Agents-of-Abyss --intent "route memory"
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli validate-candidate path/to/candidate.json
```

## Validate

```bash
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python -m pytest mcp/services/aoa-memo-mcp/tests -q
python mcp/services/aoa-memo-mcp/scripts/release_check.py
```
