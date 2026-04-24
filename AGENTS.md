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
6. `docs/SERVICE_CATALOG.md`
7. `docs/PROFILES.md`, `docs/PRESETS.md`, `docs/PATHS.md`, `docs/DEPLOYMENT.md`, `docs/FIRST_RUN.md`, `docs/RUNBOOK.md`, and `docs/SECURITY.md`
8. host, recurrence, seam, diagnostic, or repair docs relevant to the changed surface
9. `docs/AGENTS_ROOT_REFERENCE.md` for preserved full root guidance


## AGENTS stack law

- Start with this root card, then follow the nearest nested `AGENTS.md` for every touched path.
- Root guidance owns repository identity, owner boundaries, route choice, and the shortest honest verification path.
- Nested guidance owns local contracts, local risk, exact files, and local checks.
- Authored source surfaces own meaning. Generated, exported, compact, derived, runtime, and adapter surfaces summarize, transport, or support meaning.
- Self-agency, recurrence, quest, progression, checkpoint, or growth language must stay bounded, reviewable, evidence-linked, and reversible.
- Report what changed, what was verified, what was not verified, and where the next agent should resume.

## Runtime rules

- Keep the source checkout distinct from the deployed runtime root.
- Default source checkout is `~/src/abyss-stack` or `${AOA_SOURCE_ROOT}`; deployed runtime root is `/srv/abyss-stack`.
- Keep federation seams opt-in, explicit, reversible, and subordinate to owner repos.
- Do not expose secrets, widen host exposure, or perform destructive data actions without explicit operator intent and rollback posture.

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
