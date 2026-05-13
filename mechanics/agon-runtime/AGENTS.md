# AGENTS.md

Applies to `mechanics/agon-runtime/`.

This package owns the runtime-side Agon dry-run kernel and trial artifact route
inside `abyss-stack`.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, `parts/README.md`, and `PROVENANCE.md` before editing.

Archive files under `legacy/` preserve old flat named surfaces. They are
provenance and runnable local artifacts, not a new source of AoA doctrine.

Do not:

- claim live verdict, rank, scar, retention, KAG, or Tree of Sophia authority
- promote the dry-run event logs into live service behavior
- move artifacts back into flat root folders to make a validator easy
- mutate `Agents-of-Abyss`, `aoa-sdk`, or `Tree-of-Sophia` from this package

Validation:

```bash
python mechanics/agon-runtime/legacy/artifacts/scripts/build_agon_duel_runtime_kernel_registry.py --check
python mechanics/agon-runtime/legacy/artifacts/scripts/validate_agon_duel_runtime_kernels.py
python mechanics/agon-runtime/legacy/artifacts/scripts/build_agon_mechanical_trial_run_registry.py --check
python mechanics/agon-runtime/legacy/artifacts/scripts/validate_agon_mechanical_trial_runs.py
python mechanics/agon-runtime/legacy/artifacts/scripts/simulate_agon_mechanical_duel_kernel.py --check
python mechanics/agon-runtime/legacy/artifacts/scripts/simulate_agon_mechanical_trials.py --check
python -m pytest mechanics/agon-runtime/legacy/artifacts/tests
python scripts/validate_stack.py
```
