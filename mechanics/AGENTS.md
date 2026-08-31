# AGENTS.md

## Applies to

This card applies to `mechanics/` and every nested path under it until a nearer
`AGENTS.md` narrows the lane.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.
## Role

`mechanics/` is the source-owned runtime mechanics tree for abyss-stack.
It names how runtime moves are shaped, checked, handed off, and kept bounded.

It is not a live runtime directory, not a replacement for `docs/`, and not a
place for AoA, ToS, skill, memo, eval, playbook, routing, KAG, or stats
authority. Those owners remain stronger than this repository.

## Root file split

- `mechanics/AGENTS.md` owns mechanics-tree editing law and validation posture.
- `mechanics/README.md` owns the runtime mechanics atlas and package compass.
- `mechanics/ARTIFACT_TOPOLOGY.md` owns placement rules for future movement
  between root technical districts and mechanic package homes.

Root files should stay route-shaped. If a detail belongs to one mechanic, put
it in that package's `README.md`, `DIRECTION.md`, `PARTS.md`, `ROADMAP.md`,
`LANDING_LOG.md`, `PROVENANCE.md`, `parts/`, `docs/`, or a future part-local
surface.

## Package law

Every mechanics package contains:

- `AGENTS.md`
- `README.md`
- `DIRECTION.md`
- `PROVENANCE.md`
- `PARTS.md`
- `ROADMAP.md`
- `LANDING_LOG.md`
- `parts/README.md`
- `docs/README.md`

The package `README.md` is the mechanic card. It should answer when to use the
mechanic, what abyss-stack owns, which stronger owners remain outside it, what
may enter, what may leave, what must not be claimed, how to validate, and where
to route next.

`DIRECTION.md` owns current contour. `PROVENANCE.md` owns source lineage,
owner-boundary bridges, and stop-lines. `PARTS.md` owns the active
source-surface map. `parts/README.md` owns the package-local part index, and
each `parts/<part>/README.md` owns the route for that part. `ROADMAP.md` owns
future movement. `LANDING_LOG.md` records checked topology landings. `docs/`
holds package-owned prose detail when it is not a machine-readable contract,
example, generated capsule, or focused part-local test.

## Boundaries

- Keep source checkout, deployed `Configs` mirror, live runtime state, and
  machine facts distinct.
- Keep public-safe contracts separate from private host captures and secrets.
- Keep runtime seams subordinate to owner repositories.
- Do not claim live service availability from source-only documents.
- Do not move a root technical district into a package without updating
  validators and deployment sync expectations in the same change.
- Put active package-local schemas, examples, generated capsules, and focused
  tests under `parts/<part>/`, not loose package `docs/surfaces`, `generated`,
  or `tests` directories.

## Editing posture

1. Name the package being touched.
2. Keep the root atlas short and package cards specific.
3. Update the package `PARTS.md` when source surfaces move.
4. Update `parts/README.md` and the relevant `parts/<part>/README.md` when a
   part route changes.
5. Update `mechanics/ARTIFACT_TOPOLOGY.md` when placement rules change.
6. Add a decision note when topology, owner split, validator authority, or
   deployment expectations change durably.

## Validation

For mechanics-only route work,use the on-demand validation route in `VALIDATION.md`.

Validation is on-demand: use [VALIDATION.md](../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

For release-bound or runtime-facing movement, add the narrow checks named by the
touched package and the root `AGENTS.md`.

## Closeout

Report changed packages, whether documents were only routed or actually moved,
checks run, checks skipped, remaining parity risk, and the next owner route.
