# QUESTBOOK.md — abyss-stack

This file is the public tracked surface for deferred infrastructure obligations that belong to `abyss-stack`.

Use it for:
- host-profile rollout and adaptation work that survives the current diff
- render-truth, doctor, first-run, and runtime guardrail follow-through
- platform and machine-fit follow-ups
- high-risk infra obligations that must stay reviewable and human-gated

Do not use it for:
- source-owned meaning from AoA layer repos
- silent infra mutation plans
- secrets, host-local paths, or unsafe operator detail
- turning every local config experiment into a tracked quest

## Frontier / human-gated
- `ABYSS-STACK-Q-0003` — require render-truth, doctor, and first-run guardrails before risky infra mutations are delegated

## Frontier / codex-led
- `ABYSS-STACK-Q-0001` — land repo-local questbook surface with infra-specific human-gate defaults
- `ABYSS-STACK-Q-0002` — track host-profile rollout and adaptation obligations without absorbing source-owned layer meaning

## Near
- `ABYSS-STACK-Q-0004` — capture Windows bridge, reference-platform, and machine-fit follow-ups as explicit quests instead of doc drift

## Harvest candidates
- none yet

## Backing files

- `quests/*.yaml`
- `schemas/quest.schema.json`
- `schemas/quest_dispatch.schema.json`
- `examples/quest_catalog.min.example.json`
- `examples/quest_dispatch.min.example.json`

The files under `examples/*.example.json` are reviewable examples. They are not generated state, deployed runtime state, or runtime authority.
