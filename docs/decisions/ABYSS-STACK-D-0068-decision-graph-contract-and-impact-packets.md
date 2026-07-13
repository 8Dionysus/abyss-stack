# Decision Graph Contract And Impact Packets

- Decision ID: ABYSS-STACK-D-0068
- Status: accepted
- Date: 2026-06-04
- Owner surface: `scripts/validate_workspace_decision_graph.py`, `mcp/services/aoa-decisions-mcp/`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: decision graph, schema/contract, MCP access plane, validation guard
- Stack lanes: decision lane, MCP services, source validation, agent surface
- Mechanic parents: none
- Guard families: decision graph coverage, schema validation, read-only access plane, validation lane
- Posture: accepted graph-contract and impact-packet rationale

## Context

The workspace decision graph refreshes automatically and reports unknown
decision-lane surfaces. That closes cache drift, but cache freshness alone can
still hide a stale, dirty, or unpublished source checkout. Agents also need a
stronger contract for graph shape and a faster way to answer practical
questions such as "which decisions cite this source surface?" or "what records
are relevant to this changed path?"

Without a schema and impact packets, agents would keep falling back to broad
manual scans or rely on unvalidated graph structure.

## Options considered

1. Keep the graph as an informal JSON cache and use text search for impact.
2. Add a schema contract only, leaving impact lookup to generic packet search.
3. Add a schema/coverage validator and read-only MCP packets for source
   surfaces, owner surfaces, changed paths, repo coverage posture, and graph
   issues.

## Decision

Choose option 3.

Add a workspace graph schema contract and validator that checks graph JSON,
summary JSON, nodes JSONL, edges JSONL, node and edge type enums, count parity,
freshness against current decision-lane inputs, and local repo source-posture
projection.

Split freshness into local cache status and local Git source posture. Compare
HEAD only with already available local tracking refs, never fetch from this
read-only access plane, and state explicitly that remote freshness was not
checked. Source warnings degrade the MCP status but remain advisory rather than
becoming structural graph issues.

Derive stable repo identity from the local `origin` name when available so
arbitrarily named worktrees remain in the canonical repo slice. Prefer an
explicit source root when it duplicates a workspace repo identity.

Extend `aoa_decisions` with read-only impact packets for source surfaces, owner
surfaces, changed paths, repo symmetry posture, and graph issues. These routes
must auto-refresh before reading and must preserve repo-local decision records
as the strongest rationale source.

## Rationale

The graph is an agent navigation substrate, not an authority. A schema and
landing lane make the read model dependable without promoting it above source
records.

Impact packets reduce context cost and make agents less likely to miss relevant
decisions before editing source files.

## Consequences

- `ci_gate.py --mode decision-graph` becomes the focused landing lane for
  decision graph work and excludes unrelated eval checks. Because the cache is
  ignored and source posture includes HEAD, the lane refreshes the cache before
  asserting `--check` parity so it also works in a clean checkout.
- New node, edge, or surface types require schema/validator updates and tests.
- A `fresh` cache claim is scoped to `local_workspace_filesystem`; agents must
  inspect source posture before treating the graph as current repo evidence.
- Dirty, ahead, behind, diverged, and unknown source postures remain visible on
  cached reads without authorizing fetch, reset, clean, switch, or source edit.
- MCP packets remain read-only; decision creation and correction still happen
  through repo-local `docs/decisions/` files and validators.
- Repo coverage comparisons are advisory and must not force identical decision
  lane shapes across repos.

## Source surfaces

- `scripts/build_workspace_decision_graph.py`
- `scripts/validate_workspace_decision_graph.py`
- `schemas/workspace_decision_graph.schema.json`
- `schemas/workspace_decision_graph_summary.schema.json`
- `schemas/workspace_decision_graph_node.schema.json`
- `schemas/workspace_decision_graph_edge.schema.json`
- `schemas/workspace_decision_repo_source_posture.schema.json`
- `mcp/services/aoa-decisions-mcp/src/aoa_decisions_mcp/core.py`
- `mcp/services/aoa-decisions-mcp/src/aoa_decisions_mcp/server.py`
- `mcp/services/aoa-decisions-mcp/tests/test_decisions_mcp.py`
- `docs/validation/validation_lanes.json`

## Follow-up route

Update the `aoa-decision` skill chain so find/create/correct workflows use the
new impact and issue packets before broad manual scans or decision-lane writes,
and fall back to repo-local source whenever the target repo has source-posture
warnings.

## Review note: 2026-07-13

The decision was corrected after live workspace validation showed that a graph
could be cache-fresh while `aoa-skills` lagged its local `origin/main` by many
commits. The same validation also exposed worktree-directory names as unstable
repo identifiers. The source-posture and stable-identity clauses above close
those false-green paths without widening the MCP into a source mutation or
network owner.
