# Runtime Kernels

`runtime-kernels` is the active `abyss-stack` home for local Agon dry-run proof.

It owns:

- source definitions in `definitions/`
- deterministic generated registries in `generated/`
- bounded examples in `examples/`
- package-local JSON schemas in `schemas/`
- validators, simulations, and tests beside the part they prove
- recurrence observation manifests with no scheduler authority

It does not own Agon law, verdict meaning, rank, scar, retention, KAG promotion,
or Tree of Sophia promotion. Those routes stay with `Agents-of-Abyss`,
`aoa-sdk`, `aoa-memo`, `aoa-kag`, and `Tree-of-Sophia` as appropriate.

The active definitions intentionally use quiet file names. Old flat artifact
names, old landing labels, and old quest stubs are preserved only under
`../../legacy/`.

## Validation

```bash
python mechanics/agon-runtime/parts/runtime-kernels/build_duel_runtime_kernel_registry.py --check
python mechanics/agon-runtime/parts/runtime-kernels/validate_duel_runtime_kernels.py
python mechanics/agon-runtime/parts/runtime-kernels/build_mechanical_trial_run_registry.py --check
python mechanics/agon-runtime/parts/runtime-kernels/validate_mechanical_trial_runs.py
python mechanics/agon-runtime/parts/runtime-kernels/simulate_mechanical_duel_kernel.py --check
python mechanics/agon-runtime/parts/runtime-kernels/simulate_mechanical_trials.py --check
python -m pytest mechanics/agon-runtime/parts/runtime-kernels/tests
```
