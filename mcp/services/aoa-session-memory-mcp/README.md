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
- `aoa-session-memory://maintenance/status`
- `aoa-session-memory://readiness/route-layer`
- `aoa-session-memory://diagnostics/latest/{kind}`
- `aoa-session-memory://entities/{layer}`
- `aoa-session-memory://session/{session}/brief`
- `aoa-session-memory://session/{session}/manifest`
- `aoa-session-memory://session/{session}/index`
- `aoa-session-memory://session/{session}/rehydrate`
- `aoa-session-memory://route/{axis}/{key}`
- `aoa-session-memory://trace/{anchor}`
- `aoa-session-memory://hooks/receipts/{event_name}`
- `aoa-session-memory://entity-registry/{kind}`
- `aoa-session-memory://entity-lookup/{kind}/{anchor}`
- `aoa-session-memory://graph/status`
- `aoa-session-memory://graph/neighborhood/{anchor}`

Tools:

- `aoa_session_memory_status(include_live)`
- `aoa_session_search(query="", filters, limit)`; route-only search is valid when filters such as `route_signal` and `doc_type` are supplied.
- `aoa_session_agent_responses(query, session, agent_events, episode, closeout_final, verification_state, failure_state, limit)`
- `aoa_session_agent_closeouts(query, session, episode, limit)`
- `aoa_session_agent_progress_updates(query, session, episode, limit)`
- `aoa_session_agent_reasoning_windows(query, session, episode, limit, before, after)`
- `aoa_session_task_episodes(target, session, episode, status, verification_state, failure_state, limit)`
- `aoa_session_goal_lifecycles(target, session, goal_id, status, event_kind, limit, order)`
- `aoa_session_answer_neighborhood(query, session, agent_events, episode, limit, before, after)`
- `aoa_session_trace(anchor, kind, limit, per_route_limit, session, doc_type)`; the default `doc_type` is `session` for bounded live archive probes, and callers can request `event` when exact event-level evidence is needed.
- `aoa_session_entity_usage_audit(anchor, kind, limit, per_route_limit, consequence_window, document_limit, session)`
- `aoa_session_entity_usage_neighborhood(anchor, kind, limit, per_route_limit, before, after, raw_preview_chars, document_limit, session)`
- `aoa_session_entity_usage_scenario_audit(sample_size, seed, layers, min_postings, limit, per_route_limit, consequence_window, document_limit, raw_preview_limit, full)`
- `aoa_session_route(axis, key, limit, include_entry_payloads)`
- `aoa_session_brief(session, max_segments)`
- `aoa_session_retrieve(recipe, query, session, limit, event_limit)`
- `aoa_session_evidence_packet(intent, query, anchors, refs, limit)`
- `aoa_session_freshness_check(refs, session)`; pass `session` when checking session-relative refs such as `raw:line:412`.
- `aoa_session_pattern_scan(pattern, filters, limit)`
- `aoa_session_entity_inventory(layer, query, session, limit, sample_limit)`; aggregates typed session entities such as `skill`, `mcp`, `hook`, `tool`, `api`, `plugin`, `agent`, `script`, `validator`, `test`, `eval`, `git`, `playbook`, `technique`, `mechanic`, `graph`, and `memory` from route-signal indexes. This is session evidence inventory, not installed runtime inventory.
- `aoa_session_entity_registry(kind, query, lookup, limit)`; reads the generated entity registry snapshot directly for known skills, MCP services/tools, tools, APIs, hooks, scripts, validators, tests, evals, graph, and memory entities. This is a fast read-only navigation registry; `--write` refresh stays outside MCP.
- `aoa_session_hook_receipts(event_name, session, date_from, only_errors, limit)`; reads hook receipt evidence directly from `hooks/receipts.jsonl` so hook failures do not depend on noisy search or graph packets.
- `aoa_session_latest_diagnostics(kind, limit, include_payload)`
- `aoa_session_maintenance_status(deep, include_timers, full)`; returns the canonical read-only `.aoa maintenance-status` packet with `agent_route`, exact next command, search/graph posture, timer snapshot, and MCP stop line.
- `aoa_session_maintenance_plan()`; compatibility entry that returns the same maintenance-status route without timers.
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

`aoa_session_memory_status()` uses a fast search read-model presence probe. It
checks that the portable SQLite search surface, route index, atlas, and latest
diagnostic pointers are available, but it does not run global search freshness.
Use `aoa_session_freshness_check(...)` or an explicit `.aoa search-provider-status`
operator command when freshness itself is the question.

Scoped agent-event routes such as `aoa_session_agent_responses`,
`aoa_session_agent_closeouts`, `aoa_session_agent_progress_updates`,
`aoa_session_agent_reasoning_windows`, and
`aoa_session_answer_neighborhood` use the portable SQLite projection as a fast
MCP read path when the live schema supports it. These packets are bounded,
read-only, and may return zero results for a session without classified agent
events instead of starting a slow archive scan. Each fast packet carries a
`next_expansion_command` for the deeper `.aoa` route when raw before/after
windows or richer consequence analysis are needed.

`aoa_session_entity_usage_neighborhood` has the same shape for lightweight
probes: when `raw_preview_chars=0` with small limits, or when the deep archive
route times out, MCP returns a search-backed route-signal packet with refs and
a `next_expansion_command`. That keeps live agent audits bounded while leaving
raw transcript evidence authoritative.

`aoa_session_maintenance_status()` and
`aoa-session-memory://maintenance/status` are the agent decision packet for
freshness and maintenance posture. They delegate to `.aoa maintenance-status`,
remain read-only, and tell the caller whether to use graph/search, wait for
live catch-up, run operator maintenance outside MCP, or escalate to raw/deep
checks. When `.aoa` provides an `operations` summary, MCP preserves warnings,
latest search-index timings, recent problem jobs, last successful
auto-maintenance profiles, and `why_maintenance_long` evidence.

When `.aoa` is actively catching up to open Codex transcripts,
`aoa_session_freshness_check(...)` may report
`current_with_deferred_live_updates` and the provider may report
`ready_with_deferred_live_updates`. That means the last committed search/graph
snapshot is usable for routing, while the named live sessions are visible but
not asserted as fully indexed. If exact newest transcript evidence matters,
open the returned raw/session refs or run the explicit maintenance/audit route
outside MCP.

`aoa_session_memory_status(include_live=true)` additionally runs a fast
full-archive readiness gate without extracting readiness evidence samples. Full
sample-bearing `route-readiness --write-report` remains an explicit operator or
audit route outside the MCP status path.

When installed as a package, the direct server entry point is
`aoa-session-memory-mcp-server`; `aoa-session-memory-mcp` remains the CLI entry
point.

Codex discovers MCP tools and imports this package at MCP server start. A
running Codex session may keep an older tool registry and loaded Python code
after local edits. After changing tools or route dispatch, restart the Codex
session or MCP process before using live MCP output as proof. Source-local CLI
smokes with `PYTHONPATH=mcp/services/aoa-session-memory-mcp/src` prove the code
path, but they do not prove the already-open Codex MCP transport has reloaded.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
