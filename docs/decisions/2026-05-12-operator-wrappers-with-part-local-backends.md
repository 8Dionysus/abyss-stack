# 2026-05-12 Operator Wrappers With Part-Local Backends

Status: accepted
Date: 2026-05-12

## Context

`scripts/` is the stable operator command surface. It is synced into deployed
`Configs/scripts/`, named in runbooks, and used by GitHub validation. Moving
operator command names out of `scripts/` would make deployment and operator
muscle memory worse.

At the same time, keeping every implementation body in `scripts/` preserves a
flat source topology. Mechanic packages and parts now own the local route cards,
tests, schemas, docs, and package-specific validation contracts for operator
behavior, so implementation details should live near those owner surfaces.

## Options considered

1. Keep every command and implementation body in root `scripts/`.
2. Move operator command names under mechanics and require operators to relearn entrypoints.
3. Keep stable root wrappers while moving implementation bodies to owning part routes.

## Decision

Keep stable root command names in `scripts/` as thin wrappers. Move operator
implementation bodies into their owning `mechanics/<package>/parts/<part>/`
homes when the owning part is clear and deployment sync carries both the root
wrapper and backend path.

The source checkout and deployed `Configs` mirror both sync `scripts/` and
`mechanics/`, so wrappers can execute part-local backends without changing the
operator command names.

## Rationale

Stable command names are an operator and deployment contract, but implementation bodies need a local owner. Thin wrappers preserve runtime usability while part-local backends make future changes reviewable beside their docs, tests, schemas, and route cards.

## Consequences

- `scripts/` remains the public operator entrypoint district.
- Part-local backend scripts become the source-owned implementation homes for
  config projection, runtime lifecycle, diagnostic spine, machine fit,
  inference pilots, federation seams, governed execution, runtime repair, and
  Windows bridge commands.
- `scripts/validate_stack.py` checks that wrappers still point to their
  expected backend scripts.
- CI shellcheck covers both the root wrappers and the part-local backend
  scripts.
- Future commands must declare a backend route in `scripts/validate_stack.py`
  instead of leaving new implementation bodies in the root command plane.

## Source surfaces

- `scripts/README.md`
- `scripts/validate_stack.py`
- `scripts/`
- `mechanics/<package>/parts/<part>/`

## Follow-up route

Future commands should declare a stable root wrapper, a part-local backend, and validator coverage in the same change.
