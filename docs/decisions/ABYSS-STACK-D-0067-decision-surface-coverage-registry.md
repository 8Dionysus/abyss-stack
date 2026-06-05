# Decision Surface Coverage Registry

- Decision ID: ABYSS-STACK-D-0067
- Status: accepted
- Date: 2026-06-04
- Owner surface: `scripts/build_workspace_decision_graph.py`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: decision graph, generated/read-model, validation
- Stack lanes: decision lane, agent surface, source validation
- Mechanic parents: none
- Guard families: decision graph coverage, unmodeled surface detection, source freshness
- Posture: accepted coverage-registry rationale

## Context

The workspace decision graph now auto-refreshes from repo-local
`docs/decisions/` lanes and is exposed to agents through `aoa_decisions`.
Fingerprint freshness alone is not enough for long-term safety: a new file
under `docs/decisions/` can change the fingerprint while still failing to
materialize as a graph node if the builder has no explicit model for that
surface type.

That would make the cache fresh but semantically incomplete.

## Options considered

1. Keep fingerprint freshness as the only freshness contract.
2. Treat every file under `docs/decisions/` as opaque text.
3. Add an explicit decision-surface registry and fail the graph summary when a
   fingerprinted surface is not modeled or intentionally excluded.

## Decision

Choose option 3.

The workspace graph builder must classify every fingerprinted
`docs/decisions/` input as one of the supported registry entries:

- `decision_record`: top-level authored decision records parsed into
  `decision` nodes.
- `decision_lane_doc`: lane-local support docs such as `README.md`,
  `AGENTS.md`, and `TEMPLATE.md`.
- `decision_index`: generated or local lookup files under `indexes/`.

If a future file appears under `docs/decisions/` and is not covered by that
registry, the builder must emit an issue instead of silently producing a fresh
but incomplete graph.

## Rationale

The graph is meant to reduce agent cost and increase retrieval accuracy. It
cannot do that reliably if new decision-lane entities are invisible.

Explicit registry coverage keeps the read model honest without promoting it to
source authority. The source records and repo-local validators still own
meaning; the workspace graph owns discoverability and coverage reporting.

## Consequences

- Agents can inspect `decision_surface_count`, node type counts, and issue
  details to know whether the graph covered all known decision-lane inputs.
- Lane support docs and decision indexes become first-class navigation nodes.
- New nested entities, manifests, relation files, or non-standard inputs under
  `docs/decisions/` require either a registry entry or relocation outside the
  decision lane.
- MCP auto-refresh remains mandatory; unknown surfaces turn into
  `refreshed-with-issues` instead of hidden drift.

## Source surfaces

- `scripts/build_workspace_decision_graph.py`
- `tests/test_workspace_decision_graph.py`
- `mcp/services/aoa-decisions-mcp/src/aoa_decisions_mcp/core.py`
- `mcp/services/aoa-decisions-mcp/tests/test_decisions_mcp.py`
- `docs/decisions/README.md`

## Follow-up route

When a repository introduces a new durable entity type inside
`docs/decisions/`, extend the registry and add a focused workspace-graph test
before relying on that entity through `aoa_decisions`.
