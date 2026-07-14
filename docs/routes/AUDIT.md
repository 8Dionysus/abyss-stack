# Audit

This file is the repo-local audit contract for `abyss-stack`. Its canonical
path is `docs/routes/AUDIT.md`.

Read it after the root route surfaces and before repository-wide audits,
reviews, or risky source topology changes.

## Repository role

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem.

It owns:

- runtime, deployment, storage layout, lifecycle, and security posture,
- rootless Podman and systemd user orchestration,
- profile and preset composition,
- bootstrap, render, doctor, and first-run helpers,
- public-safe env examples and config-template bootstrap surfaces.

It does **not** own:

- AoA constitutional truth,
- ToS-authored knowledge meaning,
- primary truth of techniques, skills, evals, routing, memo objects, or role contracts.

## Source-of-truth docs

Default reading order for audits:

1. `AGENTS.md`
2. `README.md`
3. `CHARTER.md`
4. `BOUNDARIES.md`
5. `DESIGN.md`
6. `DESIGN.AGENTS.md` when auditing agent-facing route surfaces
7. `docs/runtime/ARCHITECTURE.md`
8. `docs/runtime/SERVICE_CATALOG.md`
9. `docs/profiles/PROFILES.md`
10. `docs/profiles/PRESETS.md`
11. `docs/profiles/PROFILE_RECIPES.md`
12. `mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`
13. `mechanics/runtime-lifecycle/parts/wait-smoke/docs/INTERNAL_PROBES.md`
14. `docs/runtime/PATHS.md`
15. `docs/runtime/STORAGE_LAYOUT.md`
16. `docs/install/DEPLOYMENT.md`
17. `docs/install/FIRST_RUN.md`
18. `mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md`
19. `mechanics/config-projection/parts/bootstrap/docs/SECRETS_BOOTSTRAP.md`
20. `docs/operations/LIFECYCLE.md`
21. `docs/operations/RUNBOOK.md`
22. `docs/operations/SECURITY.md`
23. `docs/legacy/MIGRATION_FROM_OLD.md`

Also apply the nearest nested `AGENTS.md` when working in subdirectories such as `scripts/`.

## High-risk surfaces

### Exposure and secret posture

- host-facing service binds
- internal-only probes
- env example files and config templates
- anything that could expose or render secret-bearing values
- any drift away from localhost-first and rootless defaults

### Runtime composition

- `compose/modules/`
- `compose/profiles/`
- `compose/presets/`
- render helpers and preset/profile resolution
- systemd user units
- bootstrap and first-run helpers

### Canonical path mapping

- `/srv/AbyssOS/abyss-stack` runtime root
- `Configs/` and `Secrets/` layout
- mapping between public-safe examples and live runtime files
- Windows source checkout paths versus Linux runtime paths

## Hard boundaries

Never:

- print or commit real secrets,
- read or expose secret-bearing files from live hosts,
- widen host exposure from `127.0.0.1` to `0.0.0.0` without explicit operator intent,
- perform destructive data actions without an explicit rollback path,
- merge runtime substrate meaning back into source-owned repositories,
- confuse a Windows source checkout path with the Linux runtime root,
- publish rendered config output that may contain secret-bearing values.

## Mandatory verification

### Minimum after meaningful changes

Use the root `AGENTS.md` source-validation route. The executable lane sequence
is owned by `docs/validation/validation_lanes.json`.

### When touching bootstrap, layout, env examples, or secrets mapping

Use the bootstrap and layout checks owned by `docs/install/FIRST_RUN.md`,
`docs/install/DEPLOYMENT.md`, and the runtime-lifecycle route card.

### When touching scripts

Use the syntax and shellcheck route in `scripts/AGENTS.md`. The current wrapper
and backend inventory remains in `docs/validation/script_inventory.json`.

### When touching profiles, presets, modules, or render truth

Use the smallest matching render and introspection checks owned by
`docs/profiles/PROFILES.md`, `docs/profiles/PRESETS.md`, and
`docs/profiles/PROFILE_RECIPES.md`.

Do not claim a render/bootstrap check was run unless it was actually run.

## Review guidelines

Use these severity rules for Codex GitHub review and local `/review`.

### Treat as P0

- committed live secrets or secret-bearing rendered configs
- a change that widens default host exposure beyond localhost without explicit operator intent
- a bootstrap or runtime change that can destroy data without rollback guidance

### Treat as P1

- env examples drifting away from actual runtime consumers
- path mapping drift away from `/srv/AbyssOS/abyss-stack`, `Configs`, or `Secrets`
- profile/preset/module changes without matching render/introspection verification
- hidden breaking changes in doctor/bootstrap/first-run helpers
- runtime substrate starting to author meaning that belongs in AoA or ToS
- claiming validation that was not actually run

Ignore low-value wording nits unless the task explicitly requests copyediting.

## Required report shape

Every audit or patch report for this repo should include:

### PLAN

- task restatement
- touched/inspected surfaces
- main risk: exposure, secrets, composition, paths, bootstrap, or lifecycle

### DIFF

- what changed
- whether the change affected runtime posture or only docs/metadata

### VERIFY

- root validation lane status
- any render, profile, preset, or bootstrap checks actually run
- any script syntax checks actually run
- what was not run

### REPORT

- current runtime contract after the change
- whether port exposure, secrets mapping, path mapping, or profile composition changed
- any operator follow-up required

### RESIDUAL RISK

- unverified presets/profiles
- host assumptions not exercised
- bootstrap or lifecycle paths not tested

## Routing rule

If the requested work mainly changes:

- ecosystem identity, federation rules, or cross-repo ownership, route to `Agents-of-Abyss`;
- authored knowledge architecture meaning, route to `Tree-of-Sophia`;
- bounded workflow or agent execution meaning, route to the relevant `aoa-*` repository.
