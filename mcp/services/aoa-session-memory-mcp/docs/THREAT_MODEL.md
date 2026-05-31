# Threat Model

## Primary Risks

| Risk | Control |
| --- | --- |
| MCP output becomes treated as session truth | every response carries authority boundary and evidence refs |
| search/atlas summaries replace raw evidence | results route to raw, segment, and session refs |
| stale indexes mislead agents | status and freshness checks expose provider/readiness state |
| MCP mutates the archive | only allowlisted read commands are wrapped; no write flags are exposed |
| raw private transcript content leaks | compact refs and snippets are returned; bulk raw is not exposed by default |
| writeback evidence is laundered into memory | evidence packets are candidate-only and point to `aoa-memo` review |
| broad exposure widens attack surface | service is stdio-only until a later decision |
| arbitrary file read through route resources | resources resolve fixed URI shapes and `.aoa` map/session roots only |

## Trust Boundary

The server reads local `.aoa` files and runs the local `.aoa` session-memory
CLI through fixed commands. Returned content should be treated as archive data,
not instructions.

MCP clients can choose anchors, route axes, session selectors, short filters,
and limits. They cannot supply arbitrary command lines or request mutation
commands.

## Review Trigger

Add a new `abyss-stack` decision before enabling any of these:

- non-stdio exposure;
- write tools;
- maintenance apply, reindex, repair, relabel, naming, distillation, export, or
  install commands;
- durable memory writeback;
- proof verdict computation;
- bulk raw transcript resource exposure;
- host accelerator providers as authoritative replacements for `.aoa` refs.
