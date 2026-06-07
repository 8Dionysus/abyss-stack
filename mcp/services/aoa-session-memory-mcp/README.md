# aoa-session-memory-mcp

`aoa-session-memory-mcp` exposes `.aoa` session evidence and route intelligence
through a small read-only MCP access plane.

It does not replace `.aoa`, raw transcript evidence, generated segment indexes,
atlas maps, search indexes, diagnostics, reviewed distillation, or durable
memory review. It gives agents one repeatable route to ask:

- where a stable operational anchor appeared in sessions;
- which route coordinates match a skill, MCP, hook, tool, path, repo, command,
  failure, decision, writeback pressure, goal, or pattern;
- which evidence refs support a review or debugging pass;
- whether refs and providers look fresh enough to use;
- which route map axis/key should be opened first;
- what compact session brief or retrieval packet should be read before raw
  evidence.

## Source Hierarchy

| Layer | Role |
| --- | --- |
| `.aoa` raw transcript archive | strongest session evidence |
| `.aoa` segment indexes and manifests | local event maps and technical identity |
| `.aoa` search, atlas, graph sidecar, and diagnostics | route companions and freshness/readiness evidence |
| `aoa-session-memory-mcp` | live read-only access plane over those surfaces |
| `aoa-memo` | durable reviewed memory and writeback review |

## MCP Surface

Resources:

- `aoa-session-memory://status`
- `aoa-session-memory://surfaces`
- `aoa-session-memory://provider/status`
- `aoa-session-memory://readiness/route-layer`
- `aoa-session-memory://diagnostics/latest/{kind}`
- `aoa-session-memory://session/{session}/brief`
- `aoa-session-memory://session/{session}/manifest`
- `aoa-session-memory://session/{session}/index`
- `aoa-session-memory://session/{session}/rehydrate`
- `aoa-session-memory://route/{axis}/{key}`
- `aoa-session-memory://trace/{anchor}`
- `aoa-session-memory://graph/status`
- `aoa-session-memory://graph/neighborhood/{anchor}`

Tools:

- `aoa_session_memory_status(include_live)`
- `aoa_session_search(query, filters, limit)`
- `aoa_session_trace(anchor, kind, limit, per_route_limit, session, doc_type)`; the default `doc_type` is `session` for bounded live archive probes, and callers can request `event` when exact event-level evidence is needed.
- `aoa_session_entity_usage_audit(anchor, kind, limit, per_route_limit, consequence_window, document_limit, session)`
- `aoa_session_route(axis, key, limit, include_entry_payloads)`
- `aoa_session_brief(session, max_segments)`
- `aoa_session_retrieve(recipe, query, session, limit, event_limit)`
- `aoa_session_evidence_packet(intent, query, anchors, refs, limit)`
- `aoa_session_freshness_check(refs)`
- `aoa_session_pattern_scan(pattern, filters, limit)`
- `aoa_session_latest_diagnostics(kind, limit, include_payload)`
- `aoa_session_maintenance_plan()`
- `aoa_session_graph_neighborhood(anchor, kind, depth, limit)`
- `aoa_session_graph_timeline(anchor, kind, limit)`
- `aoa_session_graph_shortest_path(source, target, kind, max_depth)`
- `aoa_session_graph_cooccurrence(anchor, kind, limit)`
- `aoa_session_graphrag_packet(query, anchor, mode, limit, include_semantic_context, rerank_local)`
- `aoa_session_explain_graph_packet(intent, anchor, query, limit)`
- `aoa_session_graph_eval(limit, include_semantic_context, rerank_local)`
- `aoa_session_graph_quality_audit(limit, sample_ref_limit, anchors, full_graphrag)`

Prompts:

- `session-rehydrate`
- `trace-agent-process`
- `debug-operational-anchor`
- `writeback-evidence-check`
- `stale-ref-repair-plan`
- `promotion-candidate-review`

All tools are read-only. They do not reindex, repair, distill, relabel,
export, promote, write memory, accept evidence, or mutate `.aoa`.

`aoa_session_memory_status(include_live=true)` runs a fast full-archive
readiness gate without extracting readiness evidence samples. Full
sample-bearing `route-readiness --write-report` remains an explicit operator or
audit route outside the MCP status path.

When installed as a package, the direct server entry point is
`aoa-session-memory-mcp-server`; `aoa-session-memory-mcp` remains the CLI entry
point.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
