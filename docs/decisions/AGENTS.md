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

## Read before editing

Read root `AGENTS.md`, then `docs/AGENTS.md`, then `docs/README.md`, then
`docs/decisions/README.md`.

For direction or release-history changes, also read root `ROADMAP.md` and
`CHANGELOG.md` so the decision note does not absorb their jobs.

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

Use the docs and release validation lane:

```bash
python scripts/generate_decision_indexes.py --check
python scripts/validate_decision_records.py
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
python -m pytest tests/test_decision_records.py
```

For release-facing direction or history changes, also run:

```bash
python -m pytest tests/test_roadmap_parity.py
```

## Closeout

Report the decision record created or the reason no record was needed, the
source surfaces that remain authoritative, and the validation run.
