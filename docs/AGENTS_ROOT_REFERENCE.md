# AGENTS root reference

This file preserves the previous full root guidance for `abyss-stack`.
The live root route card is `../AGENTS.md`.

Use this reference when:

- auditing a legacy rule from before Pack 5
- resolving a task branch that the short route card intentionally summarized
- checking whether a slimming move should become a nested `AGENTS.md`, owner doc, or validator rule

Do not treat this file as a competing root. If a preserved rule still actively governs a local directory, move or restate it at the smallest owner surface rather than re-bloating the root.

## Preserved root AGENTS.md from before Pack 5

# AGENTS.md

## Purpose

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem. It owns runtime, deployment, storage layout, lifecycle, security posture, reference-platform posture, and infrastructure glue. It supports long-horizon knowledge and agent systems without authoring their layer meaning.

This repository is where locality, recoverability, service composition, and operational discipline become concrete. It is not where ToS meaning, AoA constitutional doctrine, or playbook / skill / eval truth should be silently redefined.

## Mission

Move the stack forward without breaking locality, secrecy, recoverability, reviewability, or the Fedora-first deployment posture.

## Owns

This repository is the source of truth for:

- local and hybrid runtime topology
- rootless Podman and systemd user orchestration
- storage and mount contracts
- service modules and deployment profiles
- helper-service build contexts and bootstrap posture
- security, runbook, backup, and restore posture
- reference-platform posture, host-facts contracts, and machine-fit capture policy
- runtime-side seams, diagnostics, and repair-safe closeout surfaces that remain subordinate to owner repos

## Does not own

Do not treat this repository as the main home for:

- ecosystem identity, charter, or federation rules in `Agents-of-Abyss`
- source-linked knowledge truth in `Tree-of-Sophia`
- typed workspace integration, bounded activation, or control-plane helper behavior in `aoa-sdk`
- operator-facing companion behavior in `ATM10-Agent`
- technique, skill, eval, memo, routing, playbook, or role doctrine as primary truth
- seed staging or replay governance in `Dionysus`

If the task is mainly about layer meaning, role doctrine, or seed semantics, route there instead of teaching the runtime to impersonate the owner repo.

## Current runtime posture

Keep these living facts explicit while you work:

- deployment is Fedora-first while source work remains Windows-usable through the bridge posture
- the source checkout is `~/src/abyss-stack` by default, or `${AOA_SOURCE_ROOT}` if intentionally relocated
- the deployed runtime root is `/srv/AbyssOS/abyss-stack`
- federation seams remain opt-in, bounded, and explicit rather than magical defaults
- runtime may support continuity, recurrence, diagnostics, and repair-safe closeout, but that does not make it the owner of agent meaning, memo truth, or playbook authority

## Read first

Before changing runtime surfaces, read in this order:

1. `README.md`
2. `ROADMAP.md`
3. `CHARTER.md`
4. `BOUNDARIES.md`
5. `docs/ARCHITECTURE.md`
6. `docs/SERVICE_CATALOG.md`
7. `docs/PROFILES.md` and `docs/PRESETS.md`
8. `docs/PATHS.md`
9. `docs/DEPLOYMENT.md`, `docs/FIRST_RUN.md`, `docs/RUNBOOK.md`, and `docs/SECURITY.md`
10. `docs/REFERENCE_PLATFORM.md`, `docs/REFERENCE_PLATFORM_SPEC.md`, `docs/MACHINE_FIT_POLICY.md`, and `docs/PLATFORM_ADAPTATION_POLICY.md` when host posture or machine-fit policy is in scope
11. `docs/BRANCH_POLICY.md` and `docs/RECURRENCE_RUNTIME_POLICY.md` when recurrence or long-horizon runtime posture is touched
12. `docs/MEMO_RUNTIME_SEAM.md`, `docs/EVAL_RUNTIME_SEAM.md`, `docs/PLAYBOOK_RUNTIME_SEAM.md`, `docs/KAG_RUNTIME_SEAM.md`, `docs/ANTIFRAGILITY_RUNTIME.md`, `docs/REPAIR_SAFE_CLOSEOUT.md`, and `docs/DIAGNOSTIC_SPINE.md` when those seams are in scope
13. `docs/VIA_NEGATIVA_CHECKLIST.md` for destructive, boundary-sensitive, or ambiguity-heavy changes

If a nearer `AGENTS.md` exists for the directory you are editing, follow that file first.

## Route by intent

When the requested change is not truly runtime-owned, route by the question being asked:

- `Agents-of-Abyss` for ecosystem identity, charter, layer map, and federation rules
- `Tree-of-Sophia` for source-linked knowledge, texts, concepts, lineages, and interpretive architecture
- `aoa-sdk` for typed workspace integration, compatibility checks, bounded activation, and controlled orchestration
- `ATM10-Agent` for operator-facing companion behavior, perception, memory, voice, and controlled action
- `aoa-playbooks` for questline, campaign, and playbook-owned operational meaning
- `aoa-memo` for memo truth, recall objects, and writeback meaning
- `aoa-evals` for proof surfaces and evaluation doctrine
- `aoa-kag` for derived provenance-aware knowledge substrates
- `Dionysus` for seed staging and replay logistics

If a runtime doc starts authoring another layer's semantics, stop and reroute.

## Audit contract

For repository audits and GitHub review, read `AUDIT.md` after the core docs and also follow the nearest nested `AGENTS.md` in touched subdirectories.

## Workflow

`PLAN -> DIFF -> APPLY -> VERIFY -> REPORT`

## Hard no

- do not print or commit real secrets
- do not read or expose secret-bearing files from live hosts
- do not widen host exposure from `127.0.0.1` to `0.0.0.0` without explicit operator intent
- do not perform destructive data actions without an explicit rollback path
- do not silently merge runtime and meaning layers back together
- do not confuse a Windows source checkout path with the Linux runtime root
- do not confuse `~/src/abyss-stack` or `${AOA_SOURCE_ROOT}` with `/srv/AbyssOS/abyss-stack`
- do not convert public-safe config templates into committed secret-bearing runtime files
- do not publish rendered config output that may contain secret-bearing values
- do not commit private host-facts captures from live machines
- do not turn `aoa-doctor` into a generic inventory or monitoring program
- do not let runtime-side recurrence, quest, diagnostic, or repair surfaces become hidden sources of truth for playbook, memo, or agent doctrine
- do not smuggle live policy widening behind doc-only edits

## Default stance

- prefer minimal reversible changes
- prefer profile-aware module changes over all-stack rewrites
- prefer placeholder or skeletal files over pretending unfinished services are complete
- prefer clarity and explicit boundaries over magical automation
- prefer dry-run, repair-safe, and public-safe validation over hand-wavy confidence
- preserve `/srv/AbyssOS/abyss-stack` as the canonical deployed runtime root unless explicitly redesigned
- preserve the split between normative platform docs, public-safe host facts, and private host facts
- treat current-machine fit as a first-class runtime concern before latency-sensitive or accelerator-sensitive work
- keep federation seams opt-in, explicit, and reversible
- remember that runtime may scaffold self-agency growth, but action authority must stay bounded and inspectable

## Host-facts and root rules

- `docs/REFERENCE_PLATFORM.md` owns the intended host posture
- `docs/REFERENCE_PLATFORM_SPEC.md` owns the machine-readable contract and capture destinations
- `docs/MACHINE_FIT_POLICY.md` owns the current-machine adaptation policy and capture destinations
- `scripts/aoa-doctor` answers readiness, not durable inventory
- `scripts/aoa-host-facts` captures durable host facts
- `scripts/aoa-machine-fit` captures the bounded current-machine runtime posture
- public-safe artifacts may live under `docs/reference-platform/`
- private captures belong under `${AOA_STACK_ROOT}/Logs/host-facts/`
- private machine-fit captures belong under `${AOA_STACK_ROOT}/Logs/machine-fit/`

## Verify

- do not confuse source checkout with runtime root
- keep runtime layers distinct from layer-owned meaning
- keep public-safe docs and artifacts separate from private captures
- if paths, ports, host posture, recurrence posture, or seam behavior change, re-read the relevant governing docs before finishing
- if runtime-side seams changed, confirm they still point back to the correct owner repos instead of absorbing their doctrine
- use the narrowest dry-run or public-safe validation available for the changed scripts, modules, or docs
- if the diagnostic spine changed, also run `python scripts/build_diagnostic_surface_catalog.py --check` and `python scripts/validate_diagnostic_surface_catalog.py`

## Review guidelines

For GitHub review in this repository, treat the following as P0:

- committed live secrets or secret-bearing rendered configs
- a change that widens default host exposure beyond localhost without explicit operator intent
- a bootstrap or runtime change that can destroy data without rollback guidance

Treat the following as P1:

- env examples drifting away from actual runtime consumers
- path mapping drift away from `/srv/AbyssOS/abyss-stack`, `Configs`, or `Secrets`
- profile, preset, or module changes without matching render or introspection verification
- hidden breaking changes in doctor, bootstrap, or first-run helpers
- runtime substrate starting to author meaning that belongs in AoA or ToS
- seam docs that stop pointing back to their owner repositories
- claiming validation that was not actually run

Ignore trivial wording nits unless the task explicitly asks for copyediting.
