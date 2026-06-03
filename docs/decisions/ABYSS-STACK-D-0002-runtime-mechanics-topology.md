# Runtime Mechanics Topology

- Decision ID: ABYSS-STACK-D-0002
- Status: accepted
- Date: 2026-05-07
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-07
- Surface classes: root/topology, mechanic package
- Stack lanes: runtime mechanics
- Mechanic parents: cross-mechanic
- Guard families: runtime topology, docs route
- Posture: accepted mechanics topology rationale

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

## Options considered

1. Keep the flat source districts and rely on readers knowing file names.
2. Add a first-class `mechanics/` route tree before moving concrete artifacts.
3. Move every mechanics-owned artifact immediately in one broad pass.

## Decision

Add a top-level `mechanics/` tree for runtime mechanics.

The first wave creates route homes and package cards without moving the
established docs, scripts, schemas, examples, generated artifacts, compose
modules, or tests out of their current source districts.

Initial packages:

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
- `docs/runtime/MECHANICS.md` is a docs-side route into the mechanics tree.
- `scripts/validate_nested_agents.py` now knows the mechanics AGENTS surfaces.
- `scripts/aoa-sync-configs` and parity expectations include `mechanics/` so
  deployed `Configs` can receive the route tree after an explicit sync.
- Later waves should move concrete artifacts only with validators, links, and
  deployment sync expectations updated in the same change.

## Continuation: 2026-05-13 part-local docs topology

The next topology wave moved unambiguous part-owned mechanic documents from
package-level `docs/` directories into their owning `parts/<part>/docs/`
homes. Package `docs/README.md` files remain as route indexes rather than active
contract homes.

This continuation applies the original decision rather than replacing it:
active docs move only where an owning part already exists, validators and tests
move with the paths, and generated references such as the diagnostic surface
catalog keep pointing at the active authority surface.

Legacy-only Agon and experience-runtime artifact families stay in package-local
`legacy/` containment until a separate active contract design exists.

The same continuation also removed host-local source checkout links from
model-card docs and added a narrow validator guard against reintroducing
absolute workstation checkout paths as committed source links. The canonical
deployed runtime root remains an intentional runtime contract, not a source
checkout link.

It also added a root `systemd/` route card and README. The actual unit contract
still belongs under `systemd/user/` and `mechanics/runtime-lifecycle/`; the new
root surfaces only make the top-level folder legible.

The fast-loop Spark surface was first added for root-folder legibility and later
moved to `.agents/spark/README.md`. It does not make Spark a new owner; it only
points to the local AGENTS and SWARM surfaces for bounded fast-loop work.

`scripts/README.md` was added as a command map instead of moving root wrappers
under mechanics. Operator command names stay stable in `scripts/`; mechanic
parts own the meaning, contracts, tests, and implementation homes where moving
them is safe.

Root `docs/README.md` and `tests/README.md` were added as short indexes. They
do not create new authority; they make repo-wide docs and repo-level validation
discoverable while preserving mechanic-owned docs and tests under `mechanics/`.

Hidden source-owned districts now follow the same rule:
`.github/GITHUB_SURFACE.md` maps GitHub-native automation without competing
with the repository homepage README, and `.agents/README.md` plus
`.agents/AGENTS.md` map repo-local agent overlays. The diagnostic-spine overlay
was updated to the current part-local diagnostic paths, and the validator now
blocks stale moved mechanic doc references so hidden overlays cannot keep old
package-level docs alive.

## Source surfaces

- `mechanics/README.md`
- `docs/runtime/MECHANICS.md`
- `scripts/validate_nested_agents.py`
- `scripts/validate_stack.py`

## Follow-up route

Continue topology changes package by package, updating validators, tests, route cards, and deployment sync expectations with every artifact move.
