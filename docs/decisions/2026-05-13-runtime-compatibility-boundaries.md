# Runtime Compatibility Boundaries

Date: 2026-05-13

## Status

Accepted.

## Context

Several active runtime surfaces still need older owner-published names. Those
names are not all the same kind of debt: some are eval template IDs, some are
memo object IDs, some are SDK wire values, some are generated playbook
filenames, and some are current Dionysus seed-garden handoff paths.

Blindly renaming those values inside `abyss-stack` would break mirror,
route-api, or SDK compatibility and would pretend this repository owns sibling
source truth.

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

Use the touched package checks plus the root validation stack:

- `python -m pytest mechanics/federation-seams/parts/federation-checks/tests/test_route_api_closure_status.py mechanics/governed-execution/parts/candidate-exports/tests/test_runtime_eval_evidence_export.py mechanics/runtime-repair/parts/a2a-return-dry-run/tests/test_a2a_return_closeout_dry_run.py mechanics/runtime-repair/parts/memo-contradiction-sidecar/tests/test_memo_contradiction_integrity_runner.py -q`
- `scripts/aoa-rpg-runtime-projection --generated-only --check`
- `python scripts/validate_stack.py`
- `python scripts/validate_nested_agents.py`
