# AGENTS.md

## Applies to

This card applies to `docs/decisions/` and all descendants unless a nearer
`AGENTS.md` narrows the path.

## Role

`docs/decisions/` holds decision records for durable `abyss-stack` runtime
topology, source/runtime boundaries, validator authority, public contract, and
workflow choices.

Decision records explain why a route was chosen. Current source surfaces define
what the runtime contract is now.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Boundaries

- Do not treat this district as stronger than its source surfaces.
- Do not store operational evidence, generated reports, private captures, or
  live runtime state here.
- Do not copy sibling-owner doctrine into a local runtime decision.
- Route mechanic-local rationale to the owning mechanic package when the choice
  is not repo-wide.
- Keep old path and legacy-name detail in provenance or `legacy/` surfaces
  unless the decision itself is about the compatibility boundary.

## Decision Review Gate

Record a decision when:

- several plausible paths existed and the rationale will matter later
- a source-of-truth boundary, owner route, package topology, validator
  authority, public contract, or workflow expectation changed
- future agents are likely to repeat the same debate without a durable why

Do not record a decision when the change is tiny, self-evident, purely local, or
already explained by a stronger active source surface. In that case, closeout
should say `Decision review: no record needed` with a short reason.

Decision records must follow [TEMPLATE](TEMPLATE.md). They explain why; current
source surfaces define what.

Use canonical `ABYSS-STACK-D-####` decision IDs and full canonical-ID filenames:

```text
docs/decisions/ABYSS-STACK-D-####-kebab-title.md
```

Each record owns its `## Index Metadata`; generated lookup indexes under
`docs/decisions/indexes/` and the generated decision graph under
`docs/decisions/generated/` are read models, not rationale authority. Previous
date-prefixed paths are historical git/PR addresses only.

## Validation

Use the docs and release validation lane in [VALIDATION.md](../../VALIDATION.md).

For release-facing direction or history changes, also use the on-demand validation route in `VALIDATION.md`.


## Closeout

Report the decision record created or the reason no record was needed, the
source surfaces that remain authoritative, and the validation run.
