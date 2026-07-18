# Diagnostic Spine Validator Module

- Decision ID: ABYSS-STACK-D-0050
- Status: amended
- Amended by: `ABYSS-STACK-D-0080-diagnostic-skill-owner-home.md`
- Date: 2026-06-03
- Owner surface: `scripts/validators/diagnostic_spine.py`

## Index Metadata

- Original date: 2026-06-03
- Surface classes: validation guard, diagnostic surface, generated read-model
- Stack lanes: source checkout, runtime mechanics
- Mechanic parents: diagnostic-spine
- Guard families: validation lane, diagnostic surface catalog, owner skill package
- Posture: amended ninth validator-module split

## Context

After federation runtime seams moved out of `scripts/validate_stack.py`, the
root validator still held diagnostic-spine contracts: route docs, diagnostic
schemas, public-safe examples, generated catalog refs, and the then-local
diagnostic overlay skill posture.

Those checks protect runtime-local diagnostic read models and repair handoff
candidates. They should stay close to the diagnostic-spine owner surface
without turning the root validator into the long-term home for every schema and
example rule.

## Options considered

- Keep diagnostic-spine contracts inside `scripts/validate_stack.py`.
- Move only the generated catalog checks into the catalog validator.
- Create a focused `scripts/validators/diagnostic_spine.py` module and keep the
  root wrapper for compatibility.

## Decision

Create `scripts/validators/diagnostic_spine.py` and move the implementation of
`validate_diagnostic_spine_contracts` into it.

Keep `scripts/validate_stack.py` as the compatibility entrypoint. Update the
diagnostic surface catalog validation refs to include the focused module and
its root-level module test.

`ABYSS-STACK-D-0080` later amended the package boundary: the focused module
now validates the canonical `skills/abyss-self-diagnostic-spine` owner package
and its OS user exposure contract directly. It no longer receives a
repo-local overlay callback.

## Rationale

The diagnostic spine is a coherent owner surface: it owns self-location,
diagnostic truth-goal posture, generated catalog publication, and bounded
repair handoff readiness. Splitting it into a dedicated validator module makes
future diagnostic-schema changes targetable without widening unrelated
federation, service-selection, or source-hygiene checks.

## Consequences

- Positive: diagnostic docs, schemas, examples, catalog refs, and the canonical
  owner skill package now have a focused owner module.
- Positive: the generated diagnostic catalog names the focused validator and
  test that protect it.
- Positive: existing callers stayed stable during the extraction bridge;
  D-0063 now routes focused callers to `scripts/validators/diagnostic_spine.py`.
- Amendment: the diagnostic package no longer depends on the transitional
  `.agents/skills` projection or a callback from root orchestration.

## Source surfaces

- `scripts/validators/diagnostic_spine.py`
- `scripts/validate_stack.py`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/`
- `mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json`
- `skills/abyss-self-diagnostic-spine/`
- `skills/port.manifest.json`
- `tests/test_diagnostic_spine_validator_module.py`

## Follow-up route

Candidate next splits are machine-fit evidence checks or runtime-lifecycle
status/readout hygiene.
