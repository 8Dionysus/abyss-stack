# Decisions District

This district holds decision records explaining why a route, owner split,
runtime topology, validator authority, public contract, or workflow expectation
was chosen in `abyss-stack`.

Decision records explain why; current source surfaces define what.

## District Law

Keep this district reviewable and labeled. A reader or agent should know that a
file here is durable rationale, not current runtime law, generated evidence,
live machine state, or release history.

Use canonical `ABYSS-STACK-D-####` decision IDs and full canonical-ID filenames:

```text
docs/decisions/ABYSS-STACK-D-####-kebab-title.md
```

Previous date-prefixed decision paths are historical git/PR addresses only. Do
not recreate them as compatibility aliases.

Use [AGENTS.md](AGENTS.md) for local editing law and [TEMPLATE.md](TEMPLATE.md)
for new records.

## Current Surfaces

Generated lookup indexes live under [`indexes/`](indexes/README.md):

| Index | Use |
|---|---|
| [By number](indexes/by-number.md) | canonical sequence and file path |
| [By date](indexes/by-date.md) | original decision date |
| [By surface class](indexes/by-surface.md) | stack surface or district type |
| [By stack lane](indexes/by-stack-lane.md) | runtime, source, profile, MCP, or decision lane |
| [By mechanic parent](indexes/by-mechanic.md) | mechanic package family affected |
| [By validation or guard family](indexes/by-guard.md) | guard, validator, or workflow family |

The indexes are generated read models from each record's `## Index Metadata`.
They do not author meaning.

Generated decision graph read models live under
[`generated/`](generated/README.md):

| Graph | Use |
|---|---|
| [Decision graph JSON](generated/decision_graph.json) | machine-readable decision nodes, facet nodes, and source-surface/guard/status edges |

The graph is generated from decision metadata and source-surface lists. It does
not replace the records and does not author runtime truth.

For cross-repo agent navigation, refresh the ignored local workspace graph with:

```bash
python scripts/build_workspace_decision_graph.py --write
```

That command discovers source checkouts with `docs/decisions/` and writes
`Logs/decision-graph/latest/{workspace_decision_graph.json,nodes.jsonl,edges.jsonl,summary.json}`.
Those files are local read models for agents, not source-truth records.
Use `python scripts/build_workspace_decision_graph.py --check` to verify the
local graph is fresh after repository decision lanes move.

The workspace graph has an explicit decision-surface registry. Every
fingerprinted file under `docs/decisions/` must be modeled as a decision
record, lane support doc, decision index, or reported as an issue. Add a
registry entry before relying on a new durable entity type inside a decision
lane.

## Record Shape

New records must use [TEMPLATE.md](TEMPLATE.md). The standard shape is:

- `- Decision ID: ABYSS-STACK-D-####`
- `- Status`
- `- Date`
- `## Index Metadata`
- `## Context`
- `## Options considered`
- `## Decision`
- `## Rationale`
- `## Consequences`
- `## Source surfaces`
- `## Follow-up route`

## Must Not Claim

Do not use this district to absorb:

- current runtime direction that belongs in `ROADMAP.md`
- release-visible history that belongs in `CHANGELOG.md`
- mechanic-local direction, provenance, or landings
- live runtime receipts, private captures, logs, secrets, models, or generated
  runtime state
- sibling-owner doctrine from AoA, ToS, skills, techniques, evals, memory,
  routing, KAG, playbooks, stats, agents, or machine repositories

Do not treat a generated decision index or graph as stronger than its source
decision record, and do not treat a decision record as stronger than the
current source surface it routes to.

## Validation

Executable validation commands live in [AGENTS](AGENTS.md#validation),
including the `validate_decision_records.py` route. This README describes the
decision-record district; the route card owns the operational command list.
