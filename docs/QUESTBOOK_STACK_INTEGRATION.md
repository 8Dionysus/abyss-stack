# QUESTBOOK integration — abyss-stack

## Purpose

This note shows how `QUESTBOOK.md` fits into `abyss-stack` without confusing infra work with source-owned AoA or ToS meaning.

## Role split

- `abyss-stack` owns runtime, deployment, lifecycle, security, storage, and platform posture
- specialized AoA repositories still own their own doctrine and public meaning
- `QUESTBOOK.md` tracks deferred infra obligations that survive the current bounded diff
- high-risk routes should default toward stronger control modes and human gates

## Good anchors in this repo

Use stable anchors such as:
- `CHARTER.md`
- `BOUNDARIES.md`
- `docs/ARCHITECTURE.md`
- `docs/PROFILES.md`
- `docs/PRESETS.md`
- `docs/PROFILE_RECIPES.md`
- `docs/RPG_RUNTIME_FRONTEND_POSTURE.md`
- `docs/TOS_GRAPH_CURATION.md`
- `docs/RENDER_TRUTH.md`
- `docs/FIRST_RUN.md`
- `docs/DOCTOR.md`
- `docs/WINDOWS_BRIDGE.md`
- `docs/REFERENCE_PLATFORM.md`
- `docs/MACHINE_FIT_POLICY.md`

## Initial posture

Infra quests should answer one of these:
- which platform or profile obligation survived the current diff
- which guardrail is required before a risky mutation route
- which machine-fit or bridge follow-up must stay visible
- which runtime/frontend contract boundary must stay explicit without absorbing upstream meaning
- which route is too risky for small local wrappers and must stay human-gated

The current guarded route for risky runtime mutation is:
`aoa-doctor -> aoa-first-run --strict -> aoa-check-layout --strict -> render-truth`
before `aoa-up` or `aoa-smoke`.
If one of those gates is missing, the route stays out of delegation scope.

## Installed quest-harvest posture

`aoa-quest-harvest` may assist this repo only as a post-session installed skill after a reviewed run, closure, or pause.

- it is not used inside an active route
- it does not define orchestrator identity
- it does not replace infra ownership, playbook canon, memo writeback, or eval proof
- one anecdotal repeat is not enough to promote an infra obligation

Its allowed verdicts are:

- `keep/open quest`
- `promote to skill`
- `promote to playbook`
- `promote to orchestrator surface`
- `promote to proof surface`
- `promote to memo surface`

The example files under `examples/` stay reviewable and source-owned.
They do not become live runtime inputs, and they do not replace the deployed mirror under `/srv/AbyssOS/abyss-stack`.
