# aoa-memo-mcp

`aoa-memo-mcp` exposes OS Abyss memory through two process-isolated MCP
contours:

- read on `127.0.0.1:5421`, authenticated by the
  `aoa-memo-mcp-read-bearer-token` credential and
  `mcp:aoa-memo:read` scope;
- candidate on `127.0.0.1:5434`, authenticated by the distinct
  `aoa-memo-mcp-candidate-bearer-token` credential and
  `mcp:aoa-memo:candidate` scope.

The read catalog contains no persistent tool. The candidate catalog contains
only local candidate/index/export/forwarding-receipt helpers and no resources.

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

The complete catalogs below remain the portable/legacy surface during the
migration window. Managed HTTP selects one owner-authored capability profile:

- `durable-memory-read`: `aoa_memo_recall_brief`,
  `aoa_memo_recall_reviewed`, `aoa_memo_read_object`, and only the known-object
  resource template;
- `memory-candidate-prepare`: `aoa_memo_create_candidate`,
  `aoa_memo_prepare_intake_packet`, and
  `aoa_memo_prepare_forwarding_receipt`.

Both profiles remove prompts and every legacy helper outside the owner
manifest. The manifest is owned by
`aoa-memo:mechanics/consumer-handoff/parts/mcp-organ-access/`; this package
owns runtime binding only. Portable stdio keeps the complete contour unless a
profile is explicitly selected.

Read-contour resources:

- `aoa-memo://brief/repo/{repo}`
- `aoa-memo://memory/object/{id}`
- `aoa-memo://session/{session_id}/rehydrate`
- `aoa-memo://repo/{repo}/local-port-status`
- `aoa-memo://repo/{repo}/memo-port-index`
- `aoa-memo://repo/{repo}/memo-open-items`
- `aoa-memo://repo/{repo}/pending-exports`
- `aoa-memo://repo/{repo}/memo-vocabulary`
- `aoa-memo://intake/{packet_id}/review`

Read-contour tools:

- `aoa_memo_recall_brief(repo, intent)` for reviewed durable-memory rows only
- `aoa_memo_recall_reviewed(query, mode, limit)` for reviewed-corpus search only
- `aoa_memo_read_object(object_id)` for an exact reviewed corpus object only
- `aoa_memo_brief(repo, intent)`
- `aoa_memo_search(query, scope, mode)`
- `aoa_memo_owner_orientation(plan, memo_bundle, observed_at, target_ref,
  attempt_no)` for exact, already-admitted C08/C09 delivery plus C20; no
  reranking, reselection, persistence, effects, or hidden fallback
- `aoa_memo_validate_candidate(path)`
- `aoa_memo_build_port_index(repo, check)` without a write parameter
- `aoa_memo_validate_port(repo)`
- `aoa_memo_pending_exports(repo)`
- `aoa_memo_landing_plan(repo, export_ref, ...)` as a readiness and dry-run
  helper, not durable landing

Candidate-contour tools:

- `aoa_memo_create_candidate(repo, evidence_refs, claim)`
- `aoa_memo_write_port_index(repo)`
- `aoa_memo_prepare_intake_packet(repo, candidate_refs, receipt_refs)`
- `aoa_memo_review_intake(path)` as a local forwarding check, not durable
  review
- `aoa_memo_prepare_forwarding_receipt(path)` as the capability-profile name
  for the same bounded forwarding check

Read prompts:

- `memo-brief`
- `memo-landing-plan`
- `session-rehydrate`

Candidate prompts are `memo-intake` and `memo-review`.

Index and intake tools operate only on local `memo/` port packet state. They do
not land durable reviewed memory into `aoa-memo`. Landing-plan helpers may
prepare or run the `aoa-memo` dry-run command so agents can see whether an
export is blocked, ready, or already landed, but the durable write still happens
as an `aoa-memo` source patch with validators and review. Candidate, export,
receipt, port, and port-index packets are validated against `aoa-memo`
memory-port schemas, and packet paths must resolve under a known local
`memo/` port. Managed candidate startup also supplies an exact
`AOA_MEMO_MCP_CANDIDATE_ROOTS` application allowlist. Its systemd unit keeps
the filesystem read-only except for each admitted port's `candidates/`,
`exports/`, `receipts/`, `INDEX.md`, and `index.min.json` paths. The
`aoa-memo/memo/objects/` durable corpus is never writable by this process.

Search starts with `aoa-memo` generated memory-object read models when the
scope is `corpus`, `reviewed`, `central`, `aoa-memo`, or `all`. Use compact
field filters such as `repo:abyss-stack`, `kind:decision`,
`recall:allowed`, `source_kind:reviewed_corpus`, or `source:PORT.yaml` to keep
retrieval bounded. File hits remain supporting retrieval; source truth stays in
the reviewed object or owning repository.

The owner-orientation tool is different from generic search. `aoa-sdk` selects
the plan, `aoa-memo` authors the C08/C09 bundle, and this service only returns
the exact admitted items to the explicit caller. `off`, `fresh-start`,
silence, stale/expired admission, and rollback return an empty memory payload.
This source surface is not a deployed automatic Codex hook.

In the shared AoA Codex plane this service is registered as `aoa_memo` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. The workspace launcher
is `<workspace-root>/.codex/bin/aoa-memo-mcp-server.py`; it resolves this
stack-owned service without making `8Dionysus` the service authority.
The managed read and candidate units set `AOA_MCP_POLICY_FAMILY` to select a
disjoint catalog. Stdio defaults to the read contour; a candidate process must
be selected explicitly. When installed as a package, the direct server entry point is
`aoa-memo-mcp-server`; `aoa-memo-mcp` remains the CLI entry point.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
