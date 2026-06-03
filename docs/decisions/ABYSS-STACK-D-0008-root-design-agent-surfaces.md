# Root Design And Agent Surfaces

- Decision ID: ABYSS-STACK-D-0008
- Status: accepted
- Date: 2026-05-13
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-13
- Surface classes: root/topology, docs route
- Stack lanes: source checkout, docs and routes
- Mechanic parents: none
- Guard families: docs route
- Posture: accepted root design rationale

## Context

`abyss-stack` already had a root route card, charter, boundaries, architecture,
and mechanics atlas, but it did not have a separate design surface for the
runtime form or for the shape of agent-facing route guidance.

`Agents-of-Abyss` uses a clearer split: root `AGENTS.md` routes work,
`DESIGN.md` describes system form, and `DESIGN.AGENTS.md` describes the intended
shape of agent surfaces. The same principle is useful here, but the content must
stay runtime-specific and must not import AoA constitutional authority into
`abyss-stack`.

## Options considered

1. Keep runtime form and agent-surface form implicit in root guidance.
2. Import `Agents-of-Abyss` root design wording directly.
3. Add runtime-specific `DESIGN.md` and `DESIGN.AGENTS.md` surfaces and route root guidance through them.

## Decision

Add root `DESIGN.md` and `DESIGN.AGENTS.md` to `abyss-stack`.

- `DESIGN.md` describes the intended form of the runtime substrate: source
  checkout, deployed runtime root, config projection, service topology,
  lifecycle, machine fit, inference pilots, federation seams, diagnostics,
  repair, validators, and source/runtime authority.
- `DESIGN.AGENTS.md` describes the intended form of agent guidance: root card,
  district cards, mechanic package cards, part cards, legacy/provenance cards,
  validation surfaces, generated companions, and closeout expectations.
- Root `AGENTS.md` is reshaped as a route card that points to these design
  surfaces instead of trying to carry all design rationale itself.

## Rationale

The AoA pattern is useful because it separates route law from system form and agent-surface form. Recasting it in runtime terms gives `abyss-stack` the same clarity without importing center constitutional authority.

## Consequences

Future topology and route-card refactors should check these surfaces before
editing local packages. New root, district, mechanic, or part route cards should
prefer the canonical card shape unless a smaller local card is enough.

Validators should treat the new design files as required source surfaces and as
sync-managed public-safe docs. Runtime mirror state remains separate from source
truth; live secrets, logs, models, local databases, rendered private config, and
machine captures remain outside the GitHub mirror.

## Non-goals

- This does not move AoA doctrine into `abyss-stack`.
- This does not change deployed services or runtime state.
- This does not make generated catalogs authoritative over source surfaces.
- This does not require every existing local `AGENTS.md` to be rewritten in this
  pass.

## Source surfaces

- `DESIGN.md`
- `DESIGN.AGENTS.md`
- `AGENTS.md`
- `README.md`
- `scripts/validate_stack.py`

## Follow-up route

Revisit only if the design surfaces start duplicating root route law or importing sibling-owner doctrine into `abyss-stack`.
