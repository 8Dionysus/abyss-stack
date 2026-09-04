# AGENTS.md

Root route card for `abyss-stack`.

## Applies to

This file applies to the whole repository unless a nearer `AGENTS.md` gives a
more specific local contract.

## Role

This card owns repository identity, broad owner boundaries, source/runtime
separation, route choice, repository-wide stop-lines, and closeout shape.

It is not the runtime design or a package inventory. Read `DESIGN.md` when the
runtime form may change and `DESIGN.AGENTS.md` when agent-facing guidance may
change.

## Read before editing

1. Start with this card, then read the nearest `AGENTS.md` for every touched
   path.
2. Select the task route in
   `docs/routes/START_HERE_ROUTE_CONTRACT.md`.
3. Read only the source, owner contract, and local semantic surface needed for
   the touched claim. A README is task-conditional, not an inherited inventory.
4. Distinguish authored source, generated projection, deployed state, legacy
   material, and private machine evidence before changing or reporting them.

## Boundaries

`abyss-stack` owns runtime, deployment, storage layout, lifecycle, security
posture, reference-platform posture, MCP access planes, local runtime ports,
runtime-owned statistical questions, and infrastructure glue.

It does not own AoA constitutional doctrine, Tree of Sophia authored meaning,
SDK control-plane truth, operator companion behavior, or sibling-owned skills,
evals, memo, routing, playbooks, roles, KAG, shared stats, or seed doctrine.

Keep these locations distinct:

- source checkout: `~/src/abyss-stack` by default, or `${AOA_SOURCE_ROOT}` when
  intentionally relocated
- deployed runtime root: `/srv/AbyssOS/abyss-stack`
- deployed config tree: `/srv/AbyssOS/abyss-stack/Configs`

Never edit the deployed runtime root as if it were the source checkout.

## Validation

Use the nearest owner card to select the smallest relevant lane. Exact commands
and focused procedures live on demand in the nearest `VALIDATION.md`, with root
`VALIDATION.md` as the repository map. Preserve named lane semantics and local
stop-lines; do not copy command sequences into inherited cards.

Broaden validation when the change moves root routes, source/runtime parity,
host exposure, service lifecycle, storage, generated catalogs, or release
behavior. Report only checks actually run.

## Closeout

Report changed surfaces, semantic versus generated impact, checks run, checks
skipped, remaining risk, and the next owner route. State explicitly whether host
exposure, secrets, storage, service lifecycle, recurrence, diagnostics, repair
posture, sibling authority, or deployed state changed.

## Repository-wide stop-lines

- Authored source surfaces own meaning. Generated, exported, compact, runtime,
  and adapter surfaces may summarize or transport it but do not supersede it.
- Do not commit secrets, private captures, rendered private config, local
  databases, caches, logs, models, or live runtime state.
- Do not widen host exposure, persistence, service lifecycle, or destructive
  data scope without explicit operator intent and a rollback posture.
- Keep federation seams opt-in, explicit, reversible, and subordinate to owner
  repositories.
- Do not use legacy labels as active topology when a current package, part,
  bridge, or provenance route exists.
- Route changes in AoA doctrine, ToS meaning, or sibling-owned organs to their
  canonical repositories instead of restating them here.

## Post-change Route Review

Update only the owner surfaces whose contract actually moved:

- runtime form or source/runtime authority -> `DESIGN.md`
- agent-card form or inheritance -> `DESIGN.AGENTS.md`
- entry route meaning -> `docs/routes/START_HERE_ROUTE_CONTRACT.md` and its
  declared entry projections
- durable rationale -> `docs/decisions/`
- repository-wide direction or a future trigger -> `ROADMAP.md`
- release-visible behavior -> `CHANGELOG.md`
- generated catalogs or indexes -> their source builder and validator

Package-local landings, provenance, quests, validation, and public explanation
remain with the nearest package or district owner.

## GitHub Landing Workflow

Use `docs/governance/RELEASING.md` for branch, PR, CI, merge, and post-merge
procedure. If required status or merge authority cannot be observed, stop and
report the exact blocker rather than inferring success.

## Full reference

`docs/legacy/AGENTS_ROOT_REFERENCE.md` preserves former detailed root guidance
for audit only. It is not active route law; any surviving rule belongs in this
card or the nearest current owner surface.
