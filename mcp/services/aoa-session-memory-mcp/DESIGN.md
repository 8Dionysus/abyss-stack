# AoA Session Memory MCP Design

## Thesis

`.aoa` should be callable by OS Abyss agents as the session evidence and route
intelligence layer without copying raw archives, generated maps, or diagnostics
into every prompt.

The stable form is:

```text
anchor/query/intent -> aoa_session_memory MCP -> route candidates -> evidence refs -> freshness/readiness -> next action
```

MCP is the access layer. It is intentionally weaker than `.aoa` raw transcript
evidence, segment indexes, generated atlas maps, search provider state, and
reviewed distillation.

## Contexts

`.aoa` owns raw session evidence, compaction boundaries, segment indexes,
route-signal classification, search indexes, atlas maps, diagnostics,
rehydration, retrieval packets, graph sidecars, naming, distillation, and
promotion queues.

`aoa-session-memory-mcp` owns just-in-time read-only access, compact route
packets, freshness checks, route prompts, and MCP service packaging.

`abyss-stack` owns the runnable MCP service package and stdio topology.

`aoa-memo` owns durable reviewed memory and writeback review. This MCP may
prepare evidence refs for that route, but it does not write memory.

## Operation

An agent should be able to start from a stable operational anchor:

```text
aoa_session_trace(anchor, kind="auto", doc_type="session")
aoa_session_search(query, filters)
aoa_session_route(axis, key)
aoa_session_graph_neighborhood(anchor)
```

The anchor may be a skill, MCP, hook, tool, path, repo, command, config,
failure mode, decision thread, writeback concern, goal, or recurring pattern.
The service treats all of these as route coordinates, not as privileged object
types.

Session-level tracing is the default live probe because `.aoa` archives can be
large. Event-level tracing remains available through an explicit
`doc_type="event"` request when exact event evidence is needed.

Session review and continuation use compact packets:

```text
aoa_session_brief(session)
aoa_session_retrieve(recipe, query, session)
aoa_session_evidence_packet(intent, query, anchors, refs)
aoa_session_graphrag_packet(query, anchor)
```

Graph and GraphRAG calls are evidence-packet builders. They may expand from
lexical hits into route-signal neighborhoods, timelines, shortest paths, and
cooccurrence clusters, but they still return raw/segment/session refs instead
of final claims.

Freshness and readiness stay explicit:

```text
aoa_session_memory_status(include_live=false)
aoa_session_freshness_check(refs)
aoa_session_latest_diagnostics(kind)
aoa_session_maintenance_plan()
```

The maintenance plan is read-only. It names the operator commands that would
refresh `.aoa`, but the MCP does not run them.

The status path is intentionally cheap. When `include_live=true`, MCP runs a
full-archive readiness health gate without evidence sample extraction. The
latest saved route-readiness diagnostic remains the cached audit summary, and
sample-bearing readiness stays an explicit `.aoa` operator command rather than
a frequent MCP health check.

## Source Discovery

The service resolves the workspace root from `AOA_WORKSPACE_ROOT` or
`/srv/AbyssOS`.

The `.aoa` root resolves from `AOA_SESSION_MEMORY_ROOT` or
`<workspace-root>/.aoa`.

The archive CLI resolves from `AOA_SESSION_MEMORY_SCRIPT` or
`<aoa-root>/scripts/aoa_session_memory.py`.

## Readiness

The first layer is ready when:

- status reports portable search provider state and atlas readiness;
- trace/search return route candidates with evidence refs;
- route maps can be read by axis/key;
- graph neighborhoods, timelines, paths, cooccurrences, and GraphRAG packets
  return evidence refs without becoming authority;
- session briefs are compact and avoid bulk raw transcript output;
- retrieval and evidence packets preserve raw/segment/session refs;
- freshness checks do not claim more than they can prove;
- prompts route agents through evidence before writeback or promotion;
- validation proves the service did not become a writer, maintainer, reindexer,
  distiller, or archive authority.
