# aoa-memo-mcp

`aoa-memo-mcp` exposes OS Abyss memory through a small MCP access plane.

It does not replace `aoa-memo`, `.aoa`, or local `memo/` ports. It gives agents
one repeatable route to ask:

- what memory is relevant here;
- whether this place has a local memo port;
- how to create a candidate;
- how to validate that candidate before any durable memory landing;
- how to search reviewed corpus read models before falling back to file search;
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
- `aoa-memo://repo/{repo}/memo-port-index`
- `aoa-memo://repo/{repo}/memo-open-items`
- `aoa-memo://repo/{repo}/pending-exports`
- `aoa-memo://repo/{repo}/memo-vocabulary`
- `aoa-memo://intake/{packet_id}/review`

Tools:

- `aoa_memo_brief(repo, intent)`
- `aoa_memo_search(query, scope, mode)`
- `aoa_memo_create_candidate(repo, evidence_refs, claim)`
- `aoa_memo_validate_candidate(path)`
- `aoa_memo_build_port_index(repo, write, check)`
- `aoa_memo_validate_port(repo)`
- `aoa_memo_prepare_intake_packet(repo, candidate_refs, receipt_refs)`
- `aoa_memo_review_intake(path)` as a local forwarding check, not durable review
- `aoa_memo_pending_exports(repo)`
- `aoa_memo_landing_plan(repo, export_ref, ...)` as a readiness and dry-run
  helper, not durable landing

Prompts:

- `memo-brief`
- `memo-intake`
- `memo-review`
- `memo-landing-plan`
- `session-rehydrate`

Index and intake tools operate only on local `memo/` port packet state. They do
not land durable reviewed memory into `aoa-memo`. Landing-plan helpers may
prepare or run the `aoa-memo` dry-run command so agents can see whether an
export is blocked, ready, or already landed, but the durable write still happens
as an `aoa-memo` source patch with validators and review. Candidate, export,
receipt, port, and port-index packets are validated against `aoa-memo`
memory-port schemas, and packet paths must resolve under a known local
`memo/` port.

Search starts with `aoa-memo` generated memory-object read models when the
scope is `corpus`, `reviewed`, `central`, `aoa-memo`, or `all`. Use compact
field filters such as `repo:abyss-stack`, `kind:decision`,
`recall:allowed`, `source_kind:reviewed_corpus`, or `source:PORT.yaml` to keep
retrieval bounded. File hits remain supporting retrieval; source truth stays in
the reviewed object or owning repository.

In the shared AoA Codex plane this service is registered as `aoa_memo` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. The workspace launcher
is `<workspace-root>/.codex/bin/aoa-memo-mcp-server.py`; it resolves this
stack-owned service without making `8Dionysus` the service authority.
When installed as a package, the direct server entry point is
`aoa-memo-mcp-server`; `aoa-memo-mcp` remains the CLI entry point.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
