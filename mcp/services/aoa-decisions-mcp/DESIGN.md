# AoA Decisions MCP Design

## Thesis

Decision rationale should be fast to inspect from any repo without loading all
decision records into every prompt.

`aoa-decisions-mcp` exposes a generated workspace graph as an access plane. The
source remains each repo's `docs/decisions/` lane.

## Operation

Every resource and tool calls `ensure_fresh()` before reading graph outputs.
Freshness is based on a deterministic fingerprint of discovered workspace
decision lanes. If the fingerprint differs from the cached summary, the MCP
rebuilds the ignored local graph cache before responding.

```text
repo-local docs/decisions -> build_workspace_decision_graph.py -> Logs/decision-graph/latest -> MCP packets
```

The graph builder also owns a decision-surface registry. Every fingerprinted
file under `docs/decisions/` must either become a known graph node type or be
reported in summary issues as an unmodeled surface.

## Boundaries

- The graph is a navigation read model.
- Repo-local decision records own rationale.
- Repo-local validators and generated indexes own local decision-lane health.
- MCP writes only ignored cache files under `Logs/decision-graph/latest/`.
- Unknown decision-lane surface types require graph-registry work before agents
  rely on them through this MCP.
- Hook, timer, daemon, and durable registry installation are separate owner
  decisions.

## Agent Use

Agents should use this MCP before broad manual scans when the task involves:

- finding decision rationale;
- checking supersession or impact;
- mapping changed paths, source surfaces, or owner surfaces to related
  decisions;
- checking graph issues or cross-repo decision-lane coverage posture;
- creating or correcting a decision record;
- auditing cross-repo decision-lane symmetry;
- identifying source surfaces cited by prior decisions.

When the MCP packet points to a repo-local file, inspect that file before making
source-truth claims.
