# AUDIT.md

This file is the repo-local audit contract for `abyss-stack`.

Read it after `AGENTS.md` and before making changes.

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

1. `README.md`
2. `CHARTER.md`
3. `BOUNDARIES.md`
4. `docs/ARCHITECTURE.md`
5. `docs/SERVICE_CATALOG.md`
6. `docs/PROFILES.md`
7. `docs/PRESETS.md`
8. `docs/PROFILE_RECIPES.md`
9. `docs/RENDER_TRUTH.md`
10. `docs/INTERNAL_PROBES.md`
11. `docs/PATHS.md`
12. `docs/STORAGE_LAYOUT.md`
13. `docs/DEPLOYMENT.md`
14. `docs/FIRST_RUN.md`
15. `docs/DOCTOR.md`
16. `docs/SECRETS_BOOTSTRAP.md`
17. `docs/LIFECYCLE.md`
18. `docs/RUNBOOK.md`
19. `docs/SECURITY.md`
20. `docs/MIGRATION_FROM_OLD.md`

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

```bash
python scripts/validate_stack.py
```

### When touching bootstrap, layout, env examples, or secrets mapping

```bash
scripts/aoa-first-run --strict
scripts/aoa-check-layout --ignore-secrets
```

### When touching scripts

Run `shellcheck` on every touched shell script.

The current CI validates a broad script set including:

- `scripts/aoa-doctor`
- `scripts/aoa-install-layout`
- `scripts/aoa-sync-configs`
- `scripts/aoa-bootstrap-configs`
- `scripts/aoa-check-layout`
- `scripts/aoa-install-systemd`
- `scripts/aoa-first-run`
- `scripts/aoa-preset-profiles`
- `scripts/aoa-profile-modules`
- `scripts/aoa-profile-endpoints`
- `scripts/aoa-internal-probes`
- `scripts/aoa-render-services`
- `scripts/aoa-render-config`
- `scripts/aoa-up`
- `scripts/aoa-down`
- `scripts/aoa-status`
- `scripts/aoa-logs`
- `scripts/aoa-smoke`
- `scripts/aoa-wait`

### When touching profiles, presets, modules, or render truth

Run the smallest relevant render/introspection checks for the affected surface, for example:

```bash
scripts/aoa-profile-modules --profile core --paths
scripts/aoa-profile-endpoints --profile core
scripts/aoa-render-services --profile core
scripts/aoa-render-config --profile core >/dev/null
```

For preset changes, use the matching preset:

```bash
scripts/aoa-profile-modules --preset agent-full --paths
scripts/aoa-profile-endpoints --preset agent-full
scripts/aoa-render-services --preset agent-full
scripts/aoa-render-config --preset agent-full >/dev/null
```

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

- `python scripts/validate_stack.py` status
- any render/profile/preset/bootstrap checks actually run
- any `shellcheck` commands actually run
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
