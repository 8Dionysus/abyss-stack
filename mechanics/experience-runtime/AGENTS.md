# AGENTS.md

Applies to `mechanics/experience-runtime/`.

This package owns the `abyss-stack` runtime-side experience contract family
after the mechanics archive refactor.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, `parts/README.md`, and `PROVENANCE.md` before editing.

Archive files under `legacy/` preserve old flat named surfaces.
They are not a claim that `abyss-stack` owns experience doctrine.

Do not:

- treat adoption, governance, release, office, or polis doctrine as stack-owned
- move preserved contracts back to flat root folders without a new route
- let tests read root `schemas/` or `examples/` for this preserved family
- mutate stronger owner repos from this package

Validation:

```bash
python -m pytest mechanics/experience-runtime/legacy/artifacts/tests
python scripts/validate_stack.py
```

The archived test files keep their `test_experience_wave*_seed_contracts.py`
names until a future distillation pass creates quieter active contract tests.
