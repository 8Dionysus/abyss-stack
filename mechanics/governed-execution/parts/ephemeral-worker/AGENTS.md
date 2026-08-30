# AGENTS.md

## Applies to

This card applies to `mechanics/governed-execution/parts/ephemeral-worker/`.

## Role

This part owns the bounded runtime-side read worker and the concrete adapter
profiles for the provider-neutral delegation ABI. It is deliberately
default-off. It does not own role meaning, model fit, responsibility transfer,
proof, eval, closeout, or acceptance.

## Boundaries

- Require an explicit activation value; no automatic route or service is
  installed by this part.
- Read only explicitly listed regular files, verify their content digests, and
  enforce input and output byte ceilings.
- Return content-addressed in-memory evidence; do not mutate a workspace or
  write runtime state from the worker.
- Keep `ephemeral_read_worker_v1` parent-retained and stateless.
- Keep Codex CLI and local/provider adapters on one ABI while keeping concrete
  provider details in the adapter profile.
- Built-in Codex child-agent transport is forbidden.

## Validation

```bash
python -m pytest -q mechanics/governed-execution/parts/ephemeral-worker/tests
python -m py_compile mechanics/governed-execution/parts/ephemeral-worker/ephemeral_worker.py
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```

Real baseline, activation, pilot, promotion, and economy measurements are
separate owner-gated evidence. Focused tests do not establish them.

## Closeout

Report the exact request/result and adapter schemas, focused checks, explicit
activation posture, skipped live pilot, and the next owner route. A successful
read is runtime evidence only.
