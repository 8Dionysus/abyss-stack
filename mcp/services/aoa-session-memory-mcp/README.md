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
- `aoa-session-memory://projection/status`
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
- `aoa_session_transport_preflight()`; diagnoses portable stdio child state or
  loopback shared HTTP owner state, distinguishes stale source/config from an
  unavailable owner, rejects non-loopback or malformed HTTP endpoints, requires
  configured and available bearer authentication without exposing its value,
  distinguishes client/CLI environment readiness from owner-side systemd
  credential readiness, and reports the next action when direct calls are not
  current proof.
- `aoa_session_search(query="", filters, limit)`; route-only search is valid when filters such as `route_signal` and `doc_type` are supplied. `layer` is accepted as an input alias for `route_layer`, and explicit `use_shards`/`max_shards` filter controls are honored for bounded fan-out instead of being reported as unsupported filters. MCP returns compact hits, `mcp_route_plan`, and a provider freshness summary by default; follow `full_search_route` for the full archive CLI packet. `date_from`/`date_to` filter indexed search document/session dates; hook receipt timestamp checks should follow the returned `hook_receipts_route`.
- `aoa_session_literal_query_plan(query="", kind="auto", filters)`; plans the cheapest reliable route before broad literal raw-text search. It prefers `entity_usage_chain` for typed operational anchors, entity registry/inventory for broad class queries such as skills/MCP/hooks/tools, rehydrate plus session-scoped search for exact session ids, structured filters for exact route reads, scoped full-text shards when available, and monolith fallback only as a bounded recall safety net. The packet exposes `classifications`, `cost_profile`, `fallback_plan`, and `next_expansion_command` so agents can see why the route was selected and where to expand next.
- `aoa_session_agent_responses(query, session, agent_events, episode, closeout_final, verification_state, failure_state, limit)`
- `aoa_session_agent_closeouts(query, session, episode, limit)`
- `aoa_session_agent_progress_updates(query, session, episode, limit)`
- `aoa_session_agent_reasoning_windows(query, session, episode, limit, before, after)`
- `aoa_session_task_episodes(target, session, episode, status, verification_state, failure_state, limit)`
- `aoa_session_goal_lifecycles(target, session, goal_id, status, event_kind, limit, order)`
- `aoa_session_answer_neighborhood(query, session, agent_events, episode, limit, before, after)`
- `aoa_session_trace(anchor, kind, limit, per_route_limit, session, doc_type)`; the default `doc_type` is `session` for bounded live archive probes, and callers can request `event` when exact event-level evidence is needed.
- `aoa_session_entity_usage_chain(anchor, kind, limit, per_route_limit, consequence_window, document_limit, session, full)`; hot first packet for how a skill/MCP/hook/tool/API/etc entity was used and what happened after it. It returns compact usage-to-consequence chains, refs, freshness, noise flags, and expansion routes while skipping GraphRAG, graph neighborhood, and raw-preview neighborhoods by default. For `kind="skill"`, the compact packet preserves the producer-owned candidate evidence summary, event-level state/action semantics, and separately bounded rejected foreign-correlation events.
- `aoa_session_entity_dossier(anchor, kind, session, usage_limit, neighborhood_limit, graph_limit, graph_edge_limit)`; heavier human card for a skill/MCP/hook/tool/API/etc entity. It combines generated source identity, usage/consequence audit, before/after neighborhood, graph topology, refs, freshness/noise flags, and explicit next expansion routes without replacing raw or owner-source evidence.
- `aoa_session_entity_usage_audit(anchor, kind, limit, per_route_limit, consequence_window, document_limit, session, full)`; returns compact samples, counts, refs, freshness, and a `full_evidence_route` by default. Set `full=true` only when the caller deliberately needs the full archive evidence packet.
- `aoa_session_entity_usage_neighborhood(anchor, kind, limit, per_route_limit, before, after, raw_preview_chars, document_limit, session, full)`; returns bounded usage windows by default and keeps raw/segment evidence authoritative through refs plus `full_evidence_route`.
- `aoa_session_entity_usage_scenario_audit(sample_size, seed, layers, min_postings, limit, per_route_limit, consequence_window, document_limit, raw_preview_limit, full)`
- `aoa_session_route(axis, key, limit, include_entry_payloads)`
- `aoa_session_brief(session, max_segments)`
- `aoa_session_retrieve(recipe, query, session, limit, event_limit)`; `entity_usage`/`entity-usage-chain` requests are transparently served by the dedicated read-only `aoa_session_entity_usage_chain` route.
- `aoa_session_evidence_packet(intent, query, anchors, refs, limit)`
- `aoa_session_freshness_check(refs, session)`; pass `session` when checking session-relative refs such as `raw:line:412`.
- `aoa_session_pattern_scan(pattern, filters, limit)`
- `aoa_session_entity_inventory(layer, query, session, limit, sample_limit)`; aggregates typed session entities such as `skill`, `mcp`, `hook`, `tool`, `api`, `plugin`, `agent`, `script`, `validator`, `test`, `eval`, `git`, `playbook`, `technique`, `mechanic`, `graph`, and `memory` from route-signal indexes. Entity-registry kind names such as `mcp_service` are normalized to the matching route layer (`mcp`) on input. This is session evidence inventory, not installed runtime inventory.
- `aoa_session_entity_registry(kind, query, lookup, limit)`; reads the generated entity registry snapshot directly for known skills, MCP services/tools, tools, APIs, hooks, scripts, validators, tests, evals, graph, and memory entities. This is a fast read-only navigation registry; `--write` refresh stays outside MCP.
- `aoa_session_live_scenario_audit(seed, profiles, sample_size, recent_days, limit)`; runs a bounded multi-profile live quality loop across entity-registry lookup status, first-route entity dossier, entity usage, hook failures, goal lifecycles, agent closeouts, literal planning, graph neighborhood, graph bridge, and route-rollup query packets. The `entity_registry_lookup` profile checks active/observed/unknown live lookup plus stale/removed previous-snapshot transition probes without mutating the archive.
- `aoa_session_live_scenario_corpus_inventory(full)`; lists source-owned reviewed corpus cases without running them. Use it to choose a case/profile and read `truth_status`; it is route coverage, not live proof.
- `aoa_session_live_scenario_corpus_check(case_limit, full)`; checks the source-owned live scenario regression corpus against current route behavior and keeps warning debts visible as actionable gaps.
- `aoa_session_hook_receipts(event_name, session, date_from, only_errors, limit)`; reads hook receipt evidence directly from `hooks/receipts.jsonl` so hook failures do not depend on noisy search or graph packets. `date_from` filters receipt timestamps (`timestamp`, `received_at`, `generated_at`), not session dates.
- `aoa_session_latest_diagnostics(kind, limit, include_payload)`
- `aoa_session_maintenance_status(deep, include_timers, full)`; returns the canonical read-only `.aoa maintenance-status` packet with `agent_route`, exact next command, search/graph posture, timer snapshot, and MCP stop line.
- `aoa_session_maintenance_plan()`; compatibility entry that returns the same maintenance-status route without timers.
- `aoa_session_route_rollup_query(query, layer="tool", key, route_signal, limit, ref_limit)`; reads the materialized `.aoa` operational route-rollup projection without running maintenance, resampling shards, opening the monolith, using FTS, or hydrating raw body text. Use it when maintenance status says `use_operational_route_rollup_projection`; materialization remains an operator route outside MCP.
- `aoa_session_direct_event_rollup_query(query, usage_role="result", event_type, session_act, layer, key, route_signal, limit, ref_limit)`; reads the materialized direct operational-event rollup without running maintenance, resampling shards, opening the monolith, using FTS, or hydrating raw body text. Use it for compact event-class navigation; behavior proof still expands through `usage-chain` plus raw/segment refs.
- `aoa_session_projection_status(include_payload)`; reads the latest `projection-catchup` diagnostic and returns its `projection_completeness` block plus current maintenance summary. It does not run `projection-catchup`; that writer route stays outside MCP.
- `aoa_session_graph_neighborhood(anchor, kind, depth, limit, edge_limit)`; returns compact graph packets by default. Raise `edge_limit` only when a deeper relation walk is explicitly needed.
- `aoa_session_graph_timeline(anchor, kind, limit)`
- `aoa_session_graph_shortest_path(source, target, kind, max_depth)`
- `aoa_session_graph_bridge(source, target, kind, source_kind, target_kind, max_depth, limit)`; first compact route for "how are these two operational anchors connected?", wrapping bounded path, source/target timeline samples, refs, freshness, and next expansion.
- `aoa_session_graph_cooccurrence(anchor, kind, limit)`; bounded first route for dense operational anchors such as common tools, MCP services, hooks, or skills. It aggregates nearby route-signal cooccurrences with evidence refs without running maintenance or hydrating raw transcript bodies.
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

### Skill-evidence compact contract

`.aoa` owns skill-evidence classification. The default compact MCP audit,
usage-chain, neighborhood, and dossier packets preserve its
`skill_usage_evidence_v1` candidate summary, complete accepted-state list and
separate `rejection_edge_states`,
`skill_evidence_state`, `usage_actions` / `primary_usage_action`, bounded action
aggregates, and raw/segment/session refs. Foreign tool results with another
correlation id remain in a separate bounded `false_correlation_events` bucket
with `correlation_id`, `source_correlation_id`, and
`rejected_correlation_id`; they are not folded into accepted consequences.

These fields are navigation evidence, not a skill-effectiveness verdict. MCP
keeps `candidate_only`, `invocation_claim_allowed`, and the producer authority
boundary visible, bounds event/action samples, and does not copy arbitrary raw
transcript body fields into the response. `full=true` remains the explicit
archive expansion route when the compact samples are insufficient.

For a producer-classified Codex structured skill input, MCP preserves the
`skill_explicit_selection` entrypoint, `selected` plus `loaded` action pair,
structured-selection dimensions, bounded composite task-episode refs, and
raw/segment/session refs. Here `loaded` means only that the full skill payload
was embedded in the structured input envelope. It does not mean the model read
the skill through a file-read event, followed its procedure, completed the
task, or produced an effective outcome. Composite task-episode refs retain
session identity so equal local episode ids from different sessions do not
collapse; the link remains candidate evidence and does not permit an invocation
claim.

When the producer returns more action buckets than the compact packet can
carry, MCP applies a deterministic semantic priority. Selection/load and
behaviorally meaningful actions are retained before weak mention,
cooccurrence, or context buckets; omission counts remain explicit. This is a
transport ordering rule, not MCP-side reclassification or proof.

`aoa_session_memory_status()` uses a fast search read-model presence probe. It
checks that the portable SQLite search surface, route index, atlas, and latest
diagnostic pointers are available, but it does not run global search freshness.
Use `aoa_session_freshness_check(...)` or an explicit `.aoa search-provider-status`
operator command when freshness itself is the question.

When a direct Codex tool call fails with `Transport closed`, first run the CLI
fallback:

```bash
PYTHONPATH=mcp/services/aoa-session-memory-mcp/src python -m aoa_session_memory_mcp.cli transport-preflight
```

If it reports `direct_tool_transport_status=restart_required`, first follow its
`configured_transport_check_route`. For stdio, the package validator can prove
a freshly started source server while direct calls still need a fresh
Codex/MCP process. For shared HTTP, source/deployed parity and a fresh owner
process must be restored before direct calls count as current evidence.

Entity inventory packets include a compact `provider` summary from
`search-provider-status --provider portable_sqlite`, so agents can see whether
the atlas/search read model is current before trusting skill/MCP/hook/tool/API
inventory counts.
Wide inventory packets are bounded route packets, not full atlas dumps. They
return compact sample refs, a `route_packet`, `response_profile`, omitted
sample counts when the request exceeds the MCP sample budget, and a
`next_expansion` / `next_expansion_command` pointing to the explicit route or
search expansion that can load heavier entry payloads.

Scoped agent-event routes such as `aoa_session_agent_responses`,
`aoa_session_agent_closeouts`, `aoa_session_agent_progress_updates`,
`aoa_session_agent_reasoning_windows`, and
`aoa_session_answer_neighborhood` use the portable SQLite projection as a fast
MCP read path when the live schema supports it. These packets expose
`cost_profile`, `search_projection`, `quality`, and evidence refs, remain
bounded and read-only, and may return zero results for a session without
classified agent events instead of starting a slow archive scan. `quality`
reports agent-event counts, freshness buckets, source/read-model counts,
conversation-act counts, raw/segment ref coverage, and the latest returned
event so MCP callers can judge whether the fast packet is sufficient or should
be expanded through raw refs. Text-query fallbacks and
`next_expansion_command` use the `.aoa` shard-aware archive route
(`--use-shards --max-shards 24`) when raw before/after windows or richer
consequence analysis are needed.

`aoa_session_entity_usage_neighborhood` has the same shape for lightweight
probes: when `raw_preview_chars=0` with small limits, or when the deep archive
route times out, MCP returns a search-backed route-signal packet with refs and
a `next_expansion_command`. That keeps live agent audits bounded while leaving
raw transcript evidence authoritative. These lightweight packets are marked as
search-only probes: they do not claim that local consequence evidence is absent
unless the archive route has loaded the actual neighborhood window. Route-only
searches without text stay on the current archive search read model instead of
shard fanout so refs and freshness do not drift behind the monolith.

`aoa_session_maintenance_status()` and
`aoa-session-memory://maintenance/status` are the agent decision packet for
freshness and maintenance posture. They delegate to `.aoa maintenance-status`,
remain read-only, and tell the caller whether to use graph/search, wait for
live catch-up, run operator maintenance outside MCP, or escalate to raw/deep
checks. When `.aoa` provides an `operations` summary, MCP preserves warnings,
latest search-index timings, recent problem jobs, last successful
auto-maintenance profiles, `why_maintenance_long` evidence, and compact
search-shard raw-text fallback dependency signals. It also keeps the latest
search-shard materialization timings and bounded `slow_sessions` samples so an
agent can see which session made maintenance slow before choosing an expansion
route. The compact status packet keeps scoped full-text shard expansion
commands visible while leaving shard materialization and maintenance outside
MCP.

`aoa_session_projection_status()` and
`aoa-session-memory://projection/status` are the read-only orientation route for
post-classifier/schema catch-up. They read the latest `projection-catchup`
diagnostic, surface the compact `projection_completeness` rows, and include the
current maintenance summary. If that diagnostic is missing or stale, MCP returns
the operator command to run outside MCP instead of starting catch-up itself.

`aoa_session_graph_neighborhood(...)` first tries the generated
`graph/graph.sqlite3` store for exact route nodes such as
`route:mcp:mcp:aoa_session_memory_mcp`. That fast path follows indexed
source/target edges, compacts nodes/edges/evidence refs, reports truncation and
omitted counts, and keeps the archive `graph-neighborhood` command as
`next_expansion_command`. If the exact node or graph store is unavailable, MCP
falls back to the `.aoa` archive route. The packet remains route evidence, not
reviewed truth.
`aoa_session_graph_bridge(...)` is the MCP first move for a relation question
between two anchors. It delegates to `.aoa graph-bridge`, keeps the result
compact, and returns path/timeline refs plus freshness/noise posture instead of
claiming the graph relation as reviewed truth.

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

Codex discovers MCP tools when it attaches to the configured owner. The server
auto-reloads the `core.py` implementation for existing tools when the source
file changes, so packet logic and provider/freshness fixes do not require a
manual restart. Changes to the tool list, tool schemas, server wrapper, or
import path still require restarting the configured owner and, when the client
registry changed, the Codex client before using live output as proof.
Source-local CLI smokes prove the code path. The package validator proves a
fresh stdio process; `systemctl --user status
aoa-mcp-http@aoa-session-memory.service` is the owner check for configured
shared HTTP. A shared HTTP Codex entry must set
`bearer_token_env_var = "AOA_MCP_HTTP_BEARER_TOKEN"`, and the corresponding
credential must be present in the Codex process environment. The preflight
reports URL validity, bearer configuration, execution context, environment and
systemd-credential readiness, source conflicts, and transport-specific process
freshness without returning either bearer value. In a client/CLI context only
the environment credential proves client smoke readiness; inside the shared
owner, either its environment credential or its systemd credential may prove
owner startup readiness. It does not treat the absence of a per-Codex child as
failure when a fresh, authenticated loopback owner is configured.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
