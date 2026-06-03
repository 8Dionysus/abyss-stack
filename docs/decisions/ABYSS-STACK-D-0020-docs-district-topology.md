# Docs District Topology

- Decision ID: ABYSS-STACK-D-0020
- Status: accepted
- Date: 2026-05-14
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-14
- Surface classes: docs route, root/topology
- Stack lanes: docs and routes
- Mechanic parents: none
- Guard families: docs route
- Posture: accepted docs topology rationale

## Context

The root `docs/` directory had become a flat layer mixing route contracts,
runtime topology, source/install flow, live operation, profile selection,
governance, migration history, and preserved old root guidance. That made the
source-checkout route harder to scan and weakened the visible AbyssOS split
between public source, deployed runtime, sibling owner truth, and historical
reference material.

## Options considered

1. Keep the flat `docs/` directory and rely on `docs/README.md` to explain
   file roles.
2. Move repo-wide docs into role-named districts while keeping `docs/README.md`
   as the short dispatcher.
3. Move more content into mechanic packages immediately.

## Decision

Use role-named documentation districts:

- `docs/routes/`
- `docs/runtime/`
- `docs/install/`
- `docs/operations/`
- `docs/profiles/`
- `docs/governance/`
- `docs/legacy/`
- `docs/decisions/`

The root `docs/README.md` becomes a district map. Package-owned mechanic
doctrine still belongs under `mechanics/<package>/` or a specific part. Legacy
root guidance and old-stack migration references live under `docs/legacy/`.

## Rationale

The directory topology should show the same boundary model as the repository:
source checkout, deployed AbyssOS runtime, mechanic packages, sibling owners,
and historical provenance are related but distinct. Role-named districts reduce
duplicate root-doc routing and make it harder for package-local detail or old
reference material to drift back into the active repo-wide entry layer.

## Consequences

- Readers can enter `docs/` by job instead of scanning a flat list.
- Validators now protect the district topology instead of the old flat paths.
- Existing links and tests must follow the new homes.
- Content-level cleanup now has an owner route: refine the responsible district
  or mechanic package directly, without collapsing repo-wide docs back into a
  flat inventory.

## Source surfaces

- `docs/README.md`
- `docs/AGENTS.md`
- `docs/routes/START_HERE_ROUTE_CONTRACT.md`
- `scripts/validate_stack.py`
- `scripts/validate_nested_agents.py`

## Follow-up route

Use the owning district first. If a doc starts duplicating mechanic-owned
runtime doctrine, move the detail to the mechanic package and leave only a
route bridge in `docs/`.
