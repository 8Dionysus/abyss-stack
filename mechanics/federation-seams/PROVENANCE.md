# Federation Seams Provenance

This package descends from the runtime federation surfaces that let
`abyss-stack` consume sibling repository outputs for advisory routing,
diagnostics, and local-worker context.

The refactor pattern is:

- keep sync and check commands stable at the root wrapper surface
- keep seam-specific docs under package parts
- keep generated runtime read models under the part that builds them
- keep upstream names that are still required for compatibility in explicit
  compatibility bridges, not active topology prose

## Owner Boundary

`abyss-stack` owns runtime mirror paths, optional profile activation, route-api
consumption posture, and sync hygiene. `aoa-agents`, `aoa-memo`, `aoa-evals`,
`aoa-playbooks`, `aoa-kag`, `Tree-of-Sophia`, `Dionysus`, and other owner
repositories own the meaning of their source surfaces.

## Current Bridges

- [PARTS.md](PARTS.md) maps sibling seams to package parts.
- [parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md](parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md)
  owns active compatibility routing.
- [parts/federation-checks/legacy/upstream-compatibility/INDEX.md](parts/federation-checks/legacy/upstream-compatibility/INDEX.md)
  contains detailed legacy/upstream identifier accounting.
- [parts/rpg-runtime/README.md](parts/rpg-runtime/README.md) owns RPG runtime
  projection as a read model.
- [../config-projection/README.md](../config-projection/README.md) owns
  projection of config material that feeds runtime mirrors.
