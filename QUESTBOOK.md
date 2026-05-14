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
- none right now

## Frontier / ready
- none right now

## Near / ready
- `ABYSS-STACK-Q-0009` — restore route-api health and closure before live runtime cutover
  live-loop cutover; source/deployed parity is green, but service mutation
  remains operator-gated.

## Harvest candidates
- none yet

## Quest-harvest posture

`aoa-quest-harvest` may be installed at `.agents/skills/aoa-quest-harvest` as a post-session aid for bounded infra follow-through.

- use it only after a reviewed run, closure, or pause
- do not use it inside an active route
- it does not define orchestrator identity
- it does not replace playbook, memo, eval, or source-owned doctrine
- do not promote on one anecdotal repeat

Allowed verdicts:

- `keep/open quest`
- `promote to skill`
- `promote to playbook`
- `promote to orchestrator surface`
- `promote to proof surface`
- `promote to memo surface`

## Backing files

- `quests/<lane>/<state>/ABYSS-STACK-Q-*.yaml`
- `quests/schemas/quest.schema.json`
- `quests/schemas/quest_dispatch.schema.json`
- `quests/examples/quest_catalog.min.example.json`
- `quests/examples/quest_dispatch.min.example.json`

The files under `quests/examples/*.example.json` are reviewable examples. They are not generated state, deployed runtime state, or runtime authority.
