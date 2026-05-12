# AGENTS.md

Local guidance for `schemas/` in `abyss-stack`. Read the root `AGENTS.md` first.
This directory owns runtime-owned machine-readable contracts for the runtime substrate, not the meaning of sibling AoA or ToS layers.

## Scope

Schemas here define public, reviewable contracts for root runtime surfaces:
storage records, recurrence support, return packets, and other
infrastructure-side surfaces. Runtime lifecycle cache/usage status contracts now
live under `mechanics/runtime-lifecycle/parts/status-readouts/schemas/`. Diagnostic
spine contracts now live under
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/`. Governed execution
contracts now live under
`mechanics/governed-execution/parts/runtime-contracts/schemas/` and
`mechanics/governed-execution/parts/candidate-exports/schemas/`. Inference
benchmark contracts now live under
`mechanics/inference-pilots/parts/local-trials/schemas/`. Runtime repair active
A2A dry-run contracts now live under
`mechanics/runtime-repair/parts/a2a-return-dry-run/schemas/`. Runtime repair receipt
schemas that still carry old `_v1` names now route through
`mechanics/runtime-repair/legacy/artifacts/schemas/`. RPG runtime read-model
contracts now live under
`mechanics/federation-seams/parts/rpg-runtime/schemas/`.
They may describe how the runtime carries, stores, or proves something, but they do not make `abyss-stack` the source of truth for skill, playbook, memo, eval, role, or ToS meaning.

## Local contract

- Treat schema changes are contract changes. Call out compatibility risk in the report.
- Keep `$schema`, `$id`, required fields, enums, and version suffixes stable unless the change is intentional and reviewed.
- Pair new or changed schemas with the nearest examples, docs, generated catalogs, and tests.
- Keep runtime-side receipts subordinate to owner repos; do not encode new doctrine here just because the runtime can store it.
- Never add live secrets, private host captures, internal hostnames, or rendered runtime config values to schema examples.

## Change rules

Prefer additive fields over breaking rewrites. If a breaking change is needed, name the downstream surfaces that must move with it: docs, examples, generated catalogs, scripts, tests, and deployed config expectations.
If the change touches diagnostic or repair-safe closeout surfaces, update the
owning package-local schemas, examples, catalogs such as
`diagnostic_surface_catalog.min.json`, and builders together.

## Validate

Use the narrowest checks that cover the changed contract. Common gates:

```bash
python scripts/validate_stack.py
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
python -m pytest mechanics/runtime-repair/legacy/artifacts/tests/test_antifragility_contracts.py mechanics/diagnostic-spine/parts/diagnostic-surfaces/tests/test_diagnostic_spine_contracts.py
```
