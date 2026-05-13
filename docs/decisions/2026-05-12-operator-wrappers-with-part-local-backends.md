# 2026-05-12 Operator Wrappers With Part-Local Backends

Status: Accepted

## Context

`scripts/` is the stable operator command surface. It is synced into deployed
`Configs/scripts/`, named in runbooks, and used by GitHub validation. Moving
operator command names out of `scripts/` would make deployment and operator
muscle memory worse.

At the same time, keeping every implementation body in `scripts/` preserves a
flat source topology. Config projection and runtime lifecycle already have
owning mechanic packages and parts, so their implementation details can live
near their docs, route cards, tests, and validation contracts.

## Decision

Keep stable root command names in `scripts/` as thin wrappers. Move the
implementation bodies for config-projection and runtime-lifecycle operator
commands into their owning `mechanics/<package>/parts/<part>/` homes.

The source checkout and deployed `Configs` mirror both sync `scripts/` and
`mechanics/`, so wrappers can execute part-local backends without changing the
operator command names.

## Consequences

- `scripts/` remains the public operator entrypoint district.
- Part-local backend scripts become the source-owned implementation homes.
- `scripts/validate_stack.py` checks that wrappers still point to their
  expected backend scripts.
- CI shellcheck covers both the root wrappers and the part-local backend
  scripts.
- Future moves should follow the same pattern only when the owning part is
  clear and deployment sync carries both sides.
