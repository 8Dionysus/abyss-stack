# aoa-decisions-mcp

`aoa-decisions-mcp` exposes the workspace decision graph through a small MCP
access plane.

It does not replace `docs/decisions/`, repo-local generated indexes, or
decision validators. It gives agents one repeatable route to ask:

- which decision records match an intent, path, repo, or surface;
- which decisions cite a source surface;
- which decisions are likely impacted by a changed path;
- which records supersede or follow other records;
- which repo decision lane owns the rationale;
- which repos have comparable decision-lane coverage posture;
- which graph issues or unknown surfaces need attention;
- whether the local workspace graph is fresh and covers all known decision-lane
  input surfaces.

## Source Hierarchy

| Layer | Role |
|---|---|
| repo-local `docs/decisions/*.md` | strongest rationale source |
| repo-local decision indexes | local generated lookup read models |
| workspace decision graph | cross-repo generated navigation read model |
| `aoa-decisions-mcp` | live access plane over the graph |

## MCP Surface

Resources:

- `aoa-decisions://status`
- `aoa-decisions://summary`
- `aoa-decisions://repo/{repo}`
- `aoa-decisions://decision/{decision_id}`
- `aoa-decisions://issues`
- `aoa-decisions://issues/{repo}`

Tools:

- `aoa_decisions_status(force_refresh)`
- `aoa_decisions_summary()`
- `aoa_decisions_search(query, repo, limit)`
- `aoa_decisions_packet(query, repo, decision_id, path, limit)`
- `aoa_decisions_repo(repo)`
- `aoa_decisions_decision(decision_id, repo)`
- `aoa_decisions_source_surface(source_surface, repo, limit)`
- `aoa_decisions_owner_surface(owner_surface, repo, limit)`
- `aoa_decisions_changed_path(path, repo, limit)`
- `aoa_decisions_repo_symmetry(repo)`
- `aoa_decisions_issues(repo, limit)`
- `aoa_decisions_refresh(force)`

All read tools auto-refresh the ignored local graph cache before returning.
Refresh writes only under `Logs/decision-graph/latest/`.
If a new file appears under `docs/decisions/` without a graph-registry entry,
the refreshed summary reports an issue instead of silently hiding that surface.

## Agent Route

Executable run, smoke, and validation commands live in
[`AGENTS.md`](AGENTS.md#run). This README describes the service surface;
`AGENTS.md` owns the operational route for agents.
