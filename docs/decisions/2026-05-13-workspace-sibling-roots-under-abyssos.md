# 2026-05-13 Workspace Sibling Roots Under AbyssOS

Status: accepted
Date: 2026-05-13

## Context

`abyss-stack` is authored as a source checkout, while the local AoA / ToS
workspace is rooted under `/srv/AbyssOS`. After earlier workspace moves, some
active docs, examples, policy templates, helper defaults, and repo-local skill
symlinks still pointed at flat `/srv/<repo>` sibling roots.

Those paths are historical compatibility drift on this machine. They are not
the active workspace topology and they also break local skill discovery for
repo hooks that read `.agents/skills`.

## Options considered

1. Keep flat `/srv/<repo>` sibling roots as active defaults.
2. Switch active defaults to `/srv/AbyssOS/<repo>` while preserving env overrides.
3. Support both active root families everywhere and rely on reader judgment.

## Decision

Active workspace sibling defaults in `abyss-stack` use `/srv/AbyssOS/<repo>`.
This includes helper defaults, public-safe examples, governed policy examples,
runtime runner fallback candidates, docs, and repo-local `.agents/skills`
symlink targets.

Older flat `/srv/<repo>` sibling paths belong only in explicit legacy/archive
surfaces where they preserve lineage. They should not appear in active source
contracts.

## Rationale

The active workspace root is now `/srv/AbyssOS`, and source defaults should match that route. Environment overrides still keep portable installs possible, while validator coverage prevents the old machine-local tail from returning as active law.

## Consequences

- Environment variables can still override sibling roots for portable or
  non-standard installs.
- GitHub remains a source/install mirror; no live runtime state is synced by
  this decision.
- `scripts/validate_stack.py` blocks stale active sibling roots outside
  `legacy/` archives.
- `.agents/skills` symlinks are validated as projections into the stronger
  `aoa-skills` owner at `/srv/AbyssOS/aoa-skills/.agents/skills/`.

## Source surfaces

- `README.md`
- `docs/runtime/PATHS.md`
- `.agents/skills/`
- `scripts/validate_stack.py`

## Follow-up route

If the workspace root changes again, update path docs, helper defaults, skill projections, validators, and deployment guidance as one route change.
