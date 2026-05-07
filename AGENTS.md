# AGENTS.md

Root route card for `abyss-stack`.

## Purpose

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem.
It owns runtime, deployment, storage layout, lifecycle, security posture, reference-platform posture, and infrastructure glue.
It supports long-horizon knowledge and agent systems without authoring their layer meaning.

## Owner lane

This repository owns:

- local and hybrid runtime topology
- rootless Podman and systemd user orchestration
- storage, mounts, service modules, deployment profiles, helper-service build contexts, security, backup, restore, and runbook posture
- runtime-side diagnostics and repair-safe closeout seams subordinate to owner repos

It does not own:

- AoA constitutional doctrine, ToS authored meaning, SDK control-plane truth, operator companion behavior, or skill, eval, memo, routing, playbook, role, KAG, stats, or seed doctrine

## Start here

1. `README.md`
2. `ROADMAP.md`
3. `CHARTER.md`
4. `BOUNDARIES.md`
5. `docs/ARCHITECTURE.md`
6. `mechanics/README.md`
7. `docs/SERVICE_CATALOG.md`
8. `docs/PROFILES.md`, `docs/PRESETS.md`, `docs/PATHS.md`, `docs/DEPLOYMENT.md`, `docs/FIRST_RUN.md`, `docs/RUNBOOK.md`, and `docs/SECURITY.md`
9. host, recurrence, seam, diagnostic, repair, or mechanics docs relevant to the changed surface
10. `docs/AGENTS_ROOT_REFERENCE.md` for preserved full root guidance


## AGENTS stack law

- Start with this root card, then follow the nearest nested `AGENTS.md` for every touched path.
- Root guidance owns repository identity, owner boundaries, route choice, and the shortest honest verification path.
- Nested guidance owns local contracts, local risk, exact files, and local checks.
- Authored source surfaces own meaning. Generated, exported, compact, derived, runtime, and adapter surfaces summarize, transport, or support meaning.
- Self-agency, recurrence, quest, progression, checkpoint, or growth language must stay bounded, reviewable, evidence-linked, and reversible.
- Report what changed, what was verified, what was not verified, and where the next agent should resume.

## Runtime rules

- Keep the source checkout distinct from the deployed runtime root.
- Default source checkout is `~/src/abyss-stack` or `${AOA_SOURCE_ROOT}`; deployed runtime root is `/srv/AbyssOS/abyss-stack`.
- Keep federation seams opt-in, explicit, reversible, and subordinate to owner repos.
- Use `mechanics/README.md` when the change is about runtime move shape rather than one concrete script, compose module, or config file.
- Do not expose secrets, widen host exposure, or perform destructive data actions without explicit operator intent and rollback posture.

## GitHub landing workflow

Root `AGENTS.md` owns the repository-wide branch, PR, CI, and merge route.
`.github/AGENTS.md` owns the GitHub-native files that support it.

When the user asks to commit, push, and merge in this repository, use this route:

1. Start from a clean branch based on current `origin/main`.
2. Commit only the intended diff with a message that names the changed surface.
3. Push the branch and open a pull request with changed surfaces, validation,
   skipped checks, and remaining risk.
4. Wait for GitHub `Repo Validation` to finish. If it fails, fix the branch and
   wait for the new result.
5. Merge through GitHub after green validation. Current repository settings
   reject merge commits; use squash unless settings change. If GitHub reports a
   different allowed method for a future PR, use the allowed method and report
   which method landed.
6. Return to `main`, fast-forward from `origin/main`, and confirm the worktree is
   clean before closeout.

If GitHub status or merge permissions cannot be observed, stop the landing route
and report the exact blocker instead of guessing.

## Post-change route review

Before closeout, check whether the change actually affects these surfaces. Update
only the ones that moved; otherwise say no update was needed.

- `ROADMAP.md` when runtime direction, lifecycle posture, deployment topology,
  profile support, repair posture, or a concrete future trigger changed
- `CHANGELOG.md` when release-visible behavior, public docs, validation, or
  repository structure changed
- `docs/decisions/` when future agents need the rationale for a route,
  ownership, workflow, validator, public contract, or topology choice
- generated diagnostic surfaces, builders, validators, and tests when a
  source-backed machine capsule changed
- mechanic `LANDING_LOG.md`, `OWNER_REQUESTS.md`, `PARTS.md`, or `PROVENANCE.md`
  when a mechanic landing, owner request, active part, or legacy bridge changed
- `QUESTBOOK.md` or `quests/` when a durable obligation should survive the diff
- neighboring owner repositories when the change routes or constrains their truth

## Verify

Use the narrowest dry-run or public-safe validation for the changed scripts, modules, configs, or docs.
If paths, ports, host posture, recurrence posture, or seam behavior change, reread the governing docs before finishing.
If the diagnostic spine changes, also run:

```bash
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
```

## Report

State what runtime surface changed, whether host exposure, secrets, storage, service lifecycle, recurrence, diagnostics, or repair posture changed, and what checks ran.

## Full reference

`docs/AGENTS_ROOT_REFERENCE.md` preserves the former detailed root guidance, including current runtime posture, host-facts rules, review priorities, and default stance.
