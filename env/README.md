# env

This directory stores public-safe env examples only.

## Rules

- examples may live here
- live secrets do not live here
- examples should document names, not secret values
- examples should help bootstrap without encouraging secret leakage

## Intended mapping

- `env/stack.env.example` -> `/srv/abyss/Configs/stack.env`
- `env/langchain-api.env.example` -> `/srv/abyss/Secrets/Configs/langchain-api.env`
- `env/ovms-api.env.example` -> `/srv/abyss/Secrets/Configs/ovms-api.env`
