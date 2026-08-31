# AGENTS.md

Applies to `mechanics/experience-runtime/`.

This package owns the `abyss-stack` runtime-side experience contract family
after the mechanics archive refactor.

Read only the source and owner contract needed for the current touched surface;
`legacy/ARCHIVE_CLASSIFICATION.md`, `PROVENANCE.md`, and
`EXPERIENCE_RECORDS_DISTILLATION.md` are consulted when archive or distillation
meaning is in scope, and entering this subtree does not require an
unconditional README inventory.

Archive files under `legacy/` preserve old flat named surfaces. They are not a
claim that `abyss-stack` owns experience doctrine, and they are not active
runtime contracts until the distillation rule is satisfied.

Do not:

- treat adoption, governance, release, office, or polis doctrine as stack-owned
- move preserved contracts back to flat root folders without a new route
- promote legacy contracts without one concrete stack service, storage path, or
  operator route consuming them
- let tests read root `schemas/` or `examples/` for this preserved family
- mutate stronger owner repos from this package

Validation:

Validation is on-demand: use [VALIDATION.md](../../VALIDATION.md) for exact commands and focused checks; retain the named lane and source-owned stop-lines.

The archived test files keep their `test_experience_wave*_seed_contracts.py`
names until a future distillation pass creates quieter active contract tests.
