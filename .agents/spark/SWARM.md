# Spark Swarm Recipe — abyss-stack

Рекомендуемый путь назначения: `.agents/spark/SWARM.md`

## Для чего этот рой
Используй Spark здесь для одного infra seam: profile/preset/module alignment,
runbook/doc consistency, compose module hardening,
doctor/first-run/render-truth path или template safety. Этот рой должен двигать
стек, не ломая locality, secrecy, recoverability и Fedora-first posture.

## Читать перед стартом
- `AGENTS.md`
- `README.md`
- `CHARTER.md`
- `BOUNDARIES.md`
- `docs/ARCHITECTURE.md`
- `docs/SERVICE_CATALOG.md`
- `docs/PROFILES.md`
- `docs/PROFILE_RECIPES.md`
- `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`
- `mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md`
- `docs/FIRST_RUN.md`
- `docs/SECURITY.md`

## Форма роя
- **Coordinator**: выбирает один profile-aware infra seam
- **Scout**: картографирует modules, profiles/presets, docs и live-risk boundaries
- **Builder**: делает минимальный reversible diff
- **Verifier**: использует только repo-documented helpers for the touched surface
- **Boundary Keeper**: держит секреты, exposure, path discipline и layer separation

## Параллельные дорожки
- Lane A: compose/profile/preset/module change
- Lane B: runbook / doctor / first-run / render-truth doc sync
- Lane C: manual review of exposure, secrets, and runtime root assumptions
- Не запускай больше одного пишущего агента на одну и ту же семью файлов.

## Allowed
- чинить один profile/preset/module seam
- усиливать doc-to-script consistency
- прояснять render-truth / doctor / first-run posture
- делать minimal, reversible hardening changes

## Forbidden
- печать или коммит реальных secrets
- расширять host exposure с `127.0.0.1` до `0.0.0.0` без явного operator intent
- сливать runtime и meaning layers обратно в одну кашу
- путать Windows source checkout path с Linux runtime root
- добавлять сервисы или менять deployment topology без явного запроса
- выполнять destructive data actions без rollback path

## Launch packet для координатора
```text
We are working in abyss-stack with a one-repo one-swarm setup.
Pick exactly one infra seam:
- profile/preset/module alignment
- runbook/doc consistency
- doctor/first-run/render-truth path
- template safety
- one bounded hardening seam

First return:
1. the seam
2. exact files to touch
3. live-risk boundaries
4. which repo-documented helper(s) the verifier must use

Preserve:
PLAN -> DIFF -> APPLY -> VERIFY -> REPORT
and do not widen exposure or secrets risk.
```

## Промпт для Scout
```text
Map only. Do not edit.
Return:
- exact compose/docs/scripts files involved
- profile/preset/module relationships
- exposure/secrets/path risks
- which repo-documented helper(s) apply to this seam
- whether this requires operator confirmation instead of an autonomous edit
```

## Промпт для Builder
```text
Make the smallest reversible change.
Rules:
- prefer profile-aware module edits over all-stack rewrites
- preserve Fedora-first deployment posture
- preserve `/srv/AbyssOS/abyss-stack` as canonical deployed runtime root unless explicitly redesigned
- never create committed secret-bearing runtime files
```

## Промпт для Verifier
```text
Use only commands/helpers documented in the repo for the touched surface.
Before running anything, list the exact helper(s) you found in:
- docs/PROFILE_RECIPES.md
- mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md
- docs/FIRST_RUN.md
- mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md
- docs/RUNBOOK.md

Then run only those applicable commands and report:
- commands run
- rendered/profile outputs or doctor results
- remaining operational risks

Do not invent infra commands.
```

## Промпт для Boundary Keeper
```text
Review only for anti-scope and risk.
Check:
- no secrets exposed or committed
- no 127.0.0.1 -> 0.0.0.0 widening
- no runtime/meaning layer merge
- no Windows path confusion with Linux runtime root
- diff is minimal and reversible
```

## Verify
```bash
# Use only the exact helper commands documented for the touched surface in:
# docs/PROFILE_RECIPES.md
# mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md
# docs/FIRST_RUN.md
# mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md
# docs/RUNBOOK.md
```

## Done when
- один infra seam tightened without topology sprawl
- verifier назвал и использовал только repo-documented helper path
- exposure/secrets/path risks проверены явно
- изменение reversible and profile-aware

## Handoff
Если рой полез в service meaning, role logic или evaluation semantics, это уже соседние репо: `aoa-agents`, `aoa-skills`, `aoa-evals` или `Agents-of-Abyss`.
