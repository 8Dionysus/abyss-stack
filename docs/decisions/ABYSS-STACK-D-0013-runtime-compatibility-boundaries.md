# Runtime Compatibility Boundaries

- Decision ID: ABYSS-STACK-D-0013
- Status: accepted
- Date: 2026-05-13
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-13
- Surface classes: source/runtime boundary, validation guard
- Stack lanes: runtime mechanics
- Mechanic parents: cross-mechanic
- Guard families: source/runtime boundary, validation lane
- Posture: accepted compatibility boundary rationale

## Context

Several active runtime surfaces still need older owner-published names. Those
names are not all the same kind of debt: some are eval template IDs, some are
memo object IDs, some are SDK wire values, some are generated playbook
filenames, and some are current Dionysus seed-garden handoff paths.

Blindly renaming those values inside `abyss-stack` would break mirror,
route-api, or SDK compatibility and would pretend this repository owns sibling
source truth.

## Options considered

1. Blindly rename every old upstream value in local code and examples.
2. Keep all old upstream values as active `abyss-stack` topology.
3. Keep clean local names and isolate old upstream values behind one compatibility bridge.

## Decision

Keep clean `abyss-stack` active names at the local route boundary and preserve
old upstream names only behind one explicit compatibility bridge.

The active route card is
`mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`.
The machine-readable bridge data lives in
`config-templates/Configs/federation/upstream-compatibility-bridge.json`.
Detailed upstream IDs, lineage notes, and removal triggers live under
`mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md`.
Code that still accepts those values must isolate them behind compatibility
config reads, upstream-contract response fields, or explicit historical
fallbacks.

## Rationale

Some old values are still upstream contracts. Isolating them behind one bridge protects compatibility without letting those values leak back into active route names, docs, or local topology.

## Consequences

- Route-api and runtime adapters can continue to consume existing sibling
  mirrors without exposing old names as local topology.
- A2A return dry-run artifacts now carry clean local `request_family` and
  `request_kind` values alongside the upstream SDK compatibility kind.
- Memo contradiction sidecar reports now state which upstream eval selection,
  memo IDs, and historical log paths were consumed.
- Future cleanup should remove legacy-index entries only after the stronger
  owner publishes clean replacements and the deployed mirror moves.

## Validation

Use the touched federation, governed-execution, runtime-repair, and RPG owner
checks plus the root validation route. Exact commands remain in the nearest
`AGENTS.md` files and the validation lane manifest.

## Source surfaces

- `mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`
- `config-templates/Configs/federation/upstream-compatibility-bridge.json`
- `mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md`
- `scripts/validate_stack.py`

## Follow-up route

Retire bridge entries only after upstream owners publish clean replacements and deployed mirrors have moved to them.
