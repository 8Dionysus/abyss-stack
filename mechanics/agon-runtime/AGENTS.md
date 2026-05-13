# AGENTS.md

Applies to `mechanics/agon-runtime/`.

This package owns the runtime-side Agon dry-run kernel and trial artifact route
inside `abyss-stack`.

Read `mechanics/AGENTS.md`, this package `README.md`, `DIRECTION.md`,
`PARTS.md`, `parts/README.md`, and `PROVENANCE.md` before editing.

`parts/runtime-kernels/` owns the active dry-run definitions, generated
registries, examples, schemas, validators, simulations, tests, and recurrence
observation manifests.

Archive files under `legacy/` preserve old flat named surfaces. They are
provenance only, not the active runtime route and not a new source of AoA
doctrine.

Do not:

- claim live verdict, rank, scar, retention, KAG, or Tree of Sophia authority
- promote the dry-run event logs into live service behavior
- move artifacts back into flat root folders to make a validator easy
- mutate `Agents-of-Abyss`, `aoa-sdk`, or `Tree-of-Sophia` from this package

Validation:

```bash
python mechanics/agon-runtime/parts/runtime-kernels/build_duel_runtime_kernel_registry.py --check
python mechanics/agon-runtime/parts/runtime-kernels/validate_duel_runtime_kernels.py
python mechanics/agon-runtime/parts/runtime-kernels/build_mechanical_trial_run_registry.py --check
python mechanics/agon-runtime/parts/runtime-kernels/validate_mechanical_trial_runs.py
python mechanics/agon-runtime/parts/runtime-kernels/simulate_mechanical_duel_kernel.py --check
python mechanics/agon-runtime/parts/runtime-kernels/simulate_mechanical_trials.py --check
python -m pytest mechanics/agon-runtime/parts/runtime-kernels/tests
python scripts/validate_stack.py
```
