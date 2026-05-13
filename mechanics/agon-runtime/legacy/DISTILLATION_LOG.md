# Agon Runtime Distillation Log

## 2026-05-07

Moved the flat Agon runtime family into package-local legacy without distilling
new active doctrine.

Still legacy:

- wave landing and stop-line notes
- seed config files
- generated registry capsules
- event-log examples and contract schemas
- old `ABS-Q-AGON-*` quest stubs
- old script and test names

Future distillation should create quieter active names only when the runtime
contract is clear and validation has moved with it.

## 2026-05-13

Distilled the runnable dry-run artifact family out of `legacy/artifacts/` and
into `parts/runtime-kernels/`.

Now active:

- quiet definition files under `parts/runtime-kernels/definitions/`
- generated registry capsules under `parts/runtime-kernels/generated/`
- examples, schemas, validators, simulations, tests, and recurrence
  observation manifests under the same active part

Still legacy:

- raw `AGON_*` docs
- wave landing and stop-line notes
- old quest stubs

`legacy/artifacts/` is no longer a runnable home.
