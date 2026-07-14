# Canonical Decision IDs And Indexes

- Decision ID: ABYSS-STACK-D-0038
- Status: accepted
- Date: 2026-06-03
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: docs route, generated/readout, validation guard
- Stack lanes: decision lane, docs and routes
- Mechanic parents: none
- Guard families: decision index/read-model, docs route, validation lane
- Posture: accepted canonical cleanup

## Context

`abyss-stack` already had a populated decision district, but its active files
used date-prefixed paths and a hand-maintained README table. That was adequate
while the lane was small, but it made route recovery harder once the stack
started carrying source/runtime topology, profile posture, MCP access planes,
machine evidence gates, questbook routes, and validation law.

Sibling refactors in the AoA repository family established the stronger route:
decision records keep stable canonical handles, source notes carry lookup
metadata, and generated indexes make discovery cheaper without becoming
rationale authority.

`abyss-stack` needs that pattern in its own vocabulary. This repository already
uses `ABYSS-STACK-Q-####` for quest objects, so decision records should use the
same organ prefix with the decision object class.

## Options considered

- Keep date-prefixed filenames and only maintain the manual README table.
- Add in-file decision IDs while keeping active paths date-prefixed.
- Use full canonical decision IDs as both in-file handles and filename
  prefixes, then generate lookup indexes from stack-local metadata.

## Decision

Use full canonical IDs for `abyss-stack` decision records:

```text
ABYSS-STACK-D-####
```

Each decision note must include `- Decision ID: ABYSS-STACK-D-####`, and the
filename prefix must match the decision ID exactly:

```text
docs/decisions/ABYSS-STACK-D-####-short-slug.md
```

Each decision note also owns an `## Index Metadata` block with `Original date`,
surface classes, stack lanes, mechanic parents, guard families, and posture.
Generated lookup indexes derive from that metadata:

- `by-number.md`
- `by-date.md`
- `by-surface.md`
- `by-stack-lane.md`
- `by-mechanic.md`
- `by-guard.md`

Previous date-prefixed paths are retired. They remain recoverable through git
history, release notes, and review context, not through compatibility stubs or
active alias files.

## Rationale

Canonical IDs make decision references stable across file listings, search
results, generated read models, PR notes, memory packets, and cross-repo context
packets.

Matching filenames make the owner and object class visible from the path
itself: `ABYSS-STACK-D` means an `abyss-stack` decision, the number gives stable
order, and the slug keeps the record human-readable.

Generated indexes keep lookup cheap while preserving decision notes as the
rationale authority. The `Stack lanes` metadata is the local adaptation of the
shared pattern: it lets future agents find choices affecting runtime root,
source checkout, profiles, MCP services, machine fit, federation, diagnostics,
or the decision lane without importing proof-object, memory-object, or
skill-lane taxonomies from sibling repos.

Avoiding compatibility maps keeps the active lane small. Old date paths were
local addresses, not durable external contracts.

## Consequences

- Positive: decision records are self-identifying outside local directory
  context.
- Positive: agents can search `ABYSS-STACK-D-####` as a stable decision handle.
- Positive: date, surface, stack-lane, mechanic, and guard lookup are generated
  from source metadata.
- Tradeoff: existing date-path references outside git history must be updated
  to canonical paths.
- Follow-up: future decision notes must use the canonical ID template before
  generated index parity can pass.

## Source surfaces

- `docs/decisions/README.md`
- `docs/decisions/AGENTS.md`
- `docs/decisions/TEMPLATE.md`
- `docs/decisions/indexes/index_contract.yaml`
- `scripts/decision_indexes.py`
- `scripts/generate_decision_indexes.py`
- `scripts/validate_decision_records.py`
- `tests/test_decision_records.py`

## Follow-up route

Use `docs/decisions/AGENTS.md` and the root validation route. Exact commands
remain in the decision district route card and validation lane manifest.

Revisit this decision only if `abyss-stack` changes its decision object prefix,
generated index fields, or active decision path policy.

## Boundaries

This decision does not make generated indexes decision authority.

It does not import memory-object metadata from `aoa-memo`, proof-object fields
from `aoa-evals`, or skill-lane fields from `aoa-skills`.

It does not preserve old date-prefixed paths as active compatibility routes.

It does not change the current runtime authority of source surfaces, mechanic
packages, MCP services, profiles, or host evidence gates.
