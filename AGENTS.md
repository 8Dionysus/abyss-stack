# AGENTS.md

Root route card for `abyss-stack`.

## Applies to

This file applies to the whole repository unless a nearer `AGENTS.md` gives a
more specific local contract.

## Role

This card tells agents how to route work through `abyss-stack`. It owns
repository identity, owner boundaries, source/runtime separation, validation
choice, and closeout shape.

It is not the system design. Read `DESIGN.md` for the intended runtime form and
`DESIGN.AGENTS.md` for the intended shape of agent-facing guidance.

## Read before editing

1. `README.md`
2. `CHARTER.md`
3. `BOUNDARIES.md`
4. `DESIGN.md`
5. `DESIGN.AGENTS.md` when editing `AGENTS.md`, local route cards, or agent
   overlays
6. `docs/START_HERE_ROUTE_CONTRACT.md`
7. `ROADMAP.md`
8. `docs/ARCHITECTURE.md`
9. `mechanics/README.md`
10. The nearest local `AGENTS.md`, README, and validation notes for every touched
   path

Use `docs/AGENTS_ROOT_REFERENCE.md` only when the short card is not enough.

## Boundaries

`abyss-stack` owns runtime, deployment, storage layout, lifecycle, security
posture, reference-platform posture, and infrastructure glue.

It does not own AoA constitutional doctrine, ToS authored meaning, SDK
control-plane truth, operator companion behavior, or skill, eval, memo, routing,
playbook, role, KAG, stats, or seed doctrine.

Keep the source checkout distinct from the deployed runtime root:

- source checkout: `~/src/abyss-stack` by default, or `${AOA_SOURCE_ROOT}` when
  intentionally relocated
- deployed runtime root: `/srv/AbyssOS/abyss-stack`
- deployed config tree: `/srv/AbyssOS/abyss-stack/Configs`

Do not edit `/srv/AbyssOS/abyss-stack` as if it were the source repository.

## Validation

Use the narrowest public-safe validation for the changed surface.

For root docs, topology, validators, mechanics, or sync-managed source surfaces,
start with:

```bash
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
python -m pytest -q
```

If the diagnostic spine changes, also run:

```bash
python scripts/build_diagnostic_surface_catalog.py --check
python scripts/validate_diagnostic_surface_catalog.py
```

If source/runtime parity changes, run `python scripts/validate_stack.py
--parity-check` from the canonical source checkout, never from the deployed
`Configs` mirror.

## Closeout

Report what changed, what was verified, what was not verified, and where the
next agent should resume. Also state whether host exposure, secrets, storage,
service lifecycle, recurrence, diagnostics, repair posture, or sibling-repo
authority changed.

## Purpose

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem. It
keeps the runtime body explicit, modular, reviewable, and recoverable while
supporting long-horizon knowledge and agent systems without authoring their
layer meaning.

## Owner Lane

This repository owns:

- local and hybrid runtime topology
- rootless Podman and systemd user orchestration
- storage, mounts, service modules, deployment profiles, helper-service build
  contexts, security, backup, restore, and runbook posture
- source-to-runtime install, config projection, bootstrap, and parity contracts
- runtime-side diagnostics and repair-safe closeout seams subordinate to owner
  repositories

It does not own:

- AoA center doctrine, ToS corpus meaning, sibling repo doctrine, private live
  machine state, or semantic proof claims outside runtime-owned evidence

## Start Here

1. `README.md`
2. `CHARTER.md`
3. `BOUNDARIES.md`
4. `DESIGN.md`
5. `DESIGN.AGENTS.md`
6. `ROADMAP.md`
7. `docs/ARCHITECTURE.md`
8. `mechanics/README.md`
9. `docs/SERVICE_CATALOG.md`
10. `docs/PROFILES.md`, `docs/PRESETS.md`, `docs/PATHS.md`,
    `docs/DEPLOYMENT.md`, `docs/FIRST_RUN.md`, `docs/RUNBOOK.md`, and
    `docs/SECURITY.md`
11. Host, recurrence, seam, diagnostic, repair, or mechanics docs relevant to
    the changed surface

## Route Modes

Entry routing is governed by `docs/START_HERE_ROUTE_CONTRACT.md`. This card
keeps the working agent route; the route contract keeps public route-mode
meaning synchronized across entry surfaces.

| Need | First route |
|---|---|
| Repository orientation | `README.md` |
| Runtime system form | `DESIGN.md` |
| Agent guidance form | `DESIGN.AGENTS.md` |
| Ownership or lane dispute | `CHARTER.md` and `BOUNDARIES.md` |
| Deployment or bootstrap | `docs/DEPLOYMENT.md`, `docs/PATHS.md`, and `mechanics/config-projection/README.md` |
| Runtime lifecycle | `mechanics/runtime-lifecycle/README.md` |
| Machine fit or host bridge | `mechanics/machine-fit/README.md` |
| Local inference pilots or model trials | `mechanics/inference-pilots/README.md` |
| Federation seam | `mechanics/federation-seams/README.md` |
| Governed execution or return posture | `mechanics/governed-execution/README.md` |
| Diagnostics | `mechanics/diagnostic-spine/README.md` |
| Repair posture | `mechanics/runtime-repair/README.md` |
| Scripts | `scripts/README.md` and the owning mechanic part |
| Repo-local agent overlays | `.agents/README.md` and the nearest `.agents/**/AGENTS.md` |
| CI or GitHub route | `.github/GITHUB_SURFACE.md` and `.github/AGENTS.md` |

## AGENTS Stack Law

- Start with this root card, then follow the nearest nested `AGENTS.md` for
  every touched path.
- Root guidance owns repository identity, owner boundaries, route choice, and
  the shortest honest verification path.
- Nested guidance owns local contracts, local risk, exact files, and local
  checks.
- Authored source surfaces own meaning. Generated, exported, compact, derived,
  runtime, and adapter surfaces summarize, transport, or support meaning.
- Self-agency, recurrence, quest, progression, checkpoint, or growth language
  must stay bounded, reviewable, evidence-linked, and reversible.
- Report what changed, what was verified, what was not verified, and where the
  next agent should resume.

## Runtime Rules

- Keep federation seams opt-in, explicit, reversible, and subordinate to owner
  repos.
- Use `mechanics/README.md` when the change is about runtime move shape rather
  than one concrete script, compose module, or config file.
- Do not expose secrets, widen host exposure, or perform destructive data
  actions without explicit operator intent and rollback posture.
- Keep GitHub mirror state source-only. It may contain source, templates,
  schemas, public examples, tests, workflows, and scripts, but not live
  `Secrets/`, `Logs/`, `Models/`, `stack.env`, rendered private config, local
  databases, model files, or private captures.

## Decision Review

After a meaningful structural, ownership, workflow, route-law, validator,
public-contract, or topology change, decide whether future agents need the
rationale. If yes, add or update a note under `docs/decisions/`. If no record
is needed, say so in closeout.

## GitHub Landing Workflow

Root `AGENTS.md` owns the repository-wide branch, PR, CI, and merge route.
`.github/AGENTS.md` owns the GitHub-native files that support it.

When the user asks to commit, push, and merge in this repository, use this
route:

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
6. Return to `main`, fast-forward from `origin/main`, and confirm the worktree
   is clean before closeout.

If GitHub status or merge permissions cannot be observed, stop the landing
route and report the exact blocker instead of guessing.

## Post-change Route Review

Before closeout, check whether the change actually affects these surfaces.
Update only the ones that moved; otherwise say no update was needed.

- `DESIGN.md` when runtime form, source/runtime split, deployment shape,
  federation shape, or generated/source authority changes
- `DESIGN.AGENTS.md` when root or nested `AGENTS.md` shape, route cards, agent
  overlays, or closeout expectations change
- `README.md`, `CHARTER.md`, and `BOUNDARIES.md` when entry routing or owner
  boundaries change
- `ROADMAP.md` when runtime direction, lifecycle posture, deployment topology,
  profile support, repair posture, or a concrete future trigger changed
- `CHANGELOG.md` when release-visible behavior, public docs, validation, or
  repository structure changed
- `docs/decisions/` when future agents need the rationale for a route,
  ownership, workflow, validator, public contract, or topology choice
- generated diagnostic surfaces, builders, validators, and tests when a
  source-backed machine capsule changed
- mechanic `LANDING_LOG.md`, `OWNER_REQUESTS.md`, `PARTS.md`, or
  `PROVENANCE.md` when a mechanic landing, owner request, active part, or
  legacy bridge changed
- `QUESTBOOK.md` or `quests/` when a durable obligation should survive the diff
- neighboring owner repositories when the change routes or constrains their
  truth

## Route Away When

- The change defines AoA identity, doctrine, federation law, or program-level
  direction. Route to `Agents-of-Abyss`.
- The change authors ToS meaning, corpus structure, interpretation, or knowledge
  lineage. Route to `Tree-of-Sophia`.
- The change owns reusable techniques, skills, evals, memo objects, routing,
  playbooks, roles, KAG meaning, stats, or seed canon. Route to the matching
  `aoa-*` or sibling repository.
- The change needs private live state, secrets, logs, models, or machine-local
  captures. Keep it out of the GitHub mirror and route through runtime/operator
  actions.

## Hard No

- Do not promote live runtime state into source truth.
- Do not place secrets, private captures, local databases, caches, logs, or
  models in git.
- Do not make generated or diagnostic artifacts more authoritative than their
  source surfaces.
- Do not widen host exposure, persistence, or service lifecycle without explicit
  operator intent.
- Do not use legacy labels as active topology names when a current package,
  part, bridge, or provenance route exists.

## Review-critical Drift

Treat these as blockers until understood:

- source checkout and deployed runtime mirror disagree about authority
- root docs route to stale flat mechanics paths instead of package or part homes
- agent-facing docs skip the nearest local `AGENTS.md`
- a public doc claims live machine state, service mutation, or sibling meaning
  that the source checkout cannot prove
- a validator silently ignores a new root source surface

## Verify

Use the narrowest dry-run or public-safe validation for the changed scripts,
modules, configs, or docs. If paths, ports, host posture, recurrence posture, or
seam behavior change, reread the governing docs before finishing.

## Report

State what runtime surface changed, whether host exposure, secrets, storage,
service lifecycle, recurrence, diagnostics, or repair posture changed, and what
checks ran.

## Full Reference

`docs/AGENTS_ROOT_REFERENCE.md` preserves the former detailed root guidance,
including runtime posture, host-facts rules, review priorities, and default
stance.
