# AGENTS.md

Applies to `mechanics/experience-runtime/`.

This package owns the `abyss-stack` runtime-side experience seed contract family
after the mechanics legacy refactor.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, and `PROVENANCE.md` before editing.

Legacy files under `legacy/` preserve old flat wave, seed, and `_v1` surfaces.
They are not a claim that `abyss-stack` owns experience doctrine.

Do not:

- treat adoption, governance, release, office, or polis doctrine as stack-owned
- move `_v1` seed contracts back to flat root folders without a new route
- let tests read root `schemas/` or `examples/` for this legacy family
- mutate stronger owner repos from this package

Validation:

```bash
python -m pytest mechanics/experience-runtime/legacy/artifacts/tests
python scripts/validate_stack.py
```

The legacy test files keep their `test_experience_wave*_seed_contracts.py`
names until a future distillation pass creates quieter active contract tests.
