# 2026-05-07 Runtime Mechanics Topology

Status: Accepted

## Context

`abyss-stack` had accumulated many runtime docs, scripts, schemas, examples,
generated companions, and tests in flat source districts. That shape kept the
repository functional, but it made runtime move-types harder to see: lifecycle,
config projection, machine fit, inference pilots, federation seams, governed
execution, diagnostics, and repair-safe closeout were all discoverable only by
knowing document names.

The head AoA repository already moved center-level mechanics into a first-class
`mechanics/` route tree. `abyss-stack` needs the same convex topology pattern,
but adjusted for runtime ownership instead of center doctrine.

## Decision

Add a top-level `mechanics/` tree for runtime mechanics.

The first wave creates route homes and package cards without moving the
established docs, scripts, schemas, examples, generated artifacts, compose
modules, or tests out of their current source districts.

First-wave packages:

- `runtime-lifecycle`
- `config-projection`
- `machine-fit`
- `inference-pilots`
- `federation-seams`
- `governed-execution`
- `diagnostic-spine`
- `runtime-repair`

## Rationale

This makes the repository less flat without forcing a risky mass move while a
path-root refactor is already in the working tree. It also creates clear package
homes for later waves, so future moves can be reviewed mechanic by mechanic.

The package cards preserve the stronger owner split: runtime mechanics can
route, mirror, validate, and emit evidence, but they do not author AoA, ToS,
skill, memo, eval, playbook, routing, KAG, stats, machine, or operator truth.

## Consequences

- `mechanics/README.md` becomes the runtime move-type atlas.
- `docs/MECHANICS.md` is a docs-side route into the mechanics tree.
- `scripts/validate_nested_agents.py` now knows the mechanics AGENTS surfaces.
- `scripts/aoa-sync-configs` and parity expectations include `mechanics/` so
  deployed `Configs` can receive the route tree after an explicit sync.
- Later waves should move concrete artifacts only with validators, links, and
  deployment sync expectations updated in the same change.

