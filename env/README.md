# env

This directory stores public-safe env examples only.

## Rules

- examples may live here
- live secrets do not live here
- examples should document names, not secret values
- examples should help bootstrap without encouraging secret leakage

## Intended mapping

- `env/stack.env.example` -> `${AOA_STACK_ROOT}/Configs/stack.env`
- `env/langchain-api.env.example` -> `${AOA_STACK_ROOT}/Secrets/Configs/langchain-api.env`
- `env/ovms-api.env.example` -> `${AOA_STACK_ROOT}/Secrets/Configs/ovms-api.env`
- `env/tos-graph.env.example` -> `${AOA_STACK_ROOT}/Secrets/Configs/tos-graph.env`

## Canonical deployed default

Unless explicitly overridden, `AOA_STACK_ROOT` should resolve to:
- `/srv/AbyssOS/abyss-stack`

## See also

- `docs/SECRETS_BOOTSTRAP.md`
