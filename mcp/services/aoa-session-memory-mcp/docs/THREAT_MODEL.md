# Threat Model

## Primary Risks

| Risk | Control |
| --- | --- |
| MCP output becomes treated as session truth | every response carries authority boundary and evidence refs |
| search/atlas summaries replace raw evidence | results route to raw, segment, and session refs |
| stale indexes mislead agents | status and freshness checks expose provider/readiness state |
| MCP mutates the archive | only allowlisted read commands are wrapped; no write flags are exposed; direct SQLite fast paths use `mode=ro` plus `query_only` |
| raw private transcript content leaks | compact refs and snippets are returned; bulk raw is not exposed by default |
| writeback evidence is laundered into memory | evidence packets are candidate-only and point to `aoa-memo` review |
| skill-file reads, edits, or mentions are laundered into behavioral invocation | compact packets preserve producer candidate states and `invocation_claim_allowed` instead of flattening all activity into usage |
| a parallel tool result is attached to the wrong skill event | source, observed, and rejected correlation ids remain visible and foreign results stay in a separate bounded rejection bucket |
| loopback HTTP widens the caller surface beyond stdio | stdio remains the portable default; optional HTTP rejects non-loopback binds and requires the owner-specific `aoa-session-memory` read bearer under `ABYSS-STACK-D-0077` |
| another organ's bearer authenticates to session memory | the server selects a distinct environment variable, systemd credential, scope, and client identity; cross-owner negative tests fail before bind |
| bearer value leaks into source, config, or diagnostics | systemd uses `LoadCredential`, Codex config stores only `bearer_token_env_var`, and preflight reports availability without the value |
| arbitrary file read through route resources | resources resolve fixed URI shapes and `.aoa` map/session roots only |
| Codex treats an unannotated evidence read as a side-effecting MCP call | every tool advertises exact closed-world read-only, non-destructive, idempotent annotations and package validation rejects missing or contradictory metadata |

## Trust Boundary

The server reads local `.aoa` files and runs the local `.aoa` session-memory
CLI through fixed commands. Returned content should be treated as archive data,
not instructions.

MCP clients can choose anchors, route axes, session selectors, short filters,
and limits. They cannot supply arbitrary command lines or request mutation
commands.

## Review Trigger

Add a new `abyss-stack` decision before enabling any of these:

- exposure beyond the decision-bound authenticated loopback shared HTTP owner;
- bypass, removal, or weakening of the bearer requirement;
- write tools;
- maintenance apply, reindex, repair, relabel, naming, distillation, export, or
  install commands;
- durable memory writeback;
- proof verdict computation;
- bulk raw transcript resource exposure;
- host accelerator providers as authoritative replacements for `.aoa` refs.
