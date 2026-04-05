# AGENTS.md

## Purpose

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem. It owns runtime, deployment, storage, lifecycle, reference-platform posture, and infrastructure glue. It does not own layer meaning.

## Mission

Move the stack forward without breaking locality, secrecy, recoverability, or the Fedora-first deployment posture.

## Read first

1. `README.md`
2. `CHARTER.md`
3. `BOUNDARIES.md`
4. `docs/ARCHITECTURE.md`
5. `docs/SERVICE_CATALOG.md`
6. `docs/PROFILES.md`
7. `docs/PRESETS.md`
8. `docs/PATHS.md`
9. `docs/DEPLOYMENT.md`
10. `docs/RUNBOOK.md`
11. `docs/SECURITY.md`

If a nearer `AGENTS.md` exists for the directory you are editing, follow that file first.

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
- do not confuse `~/src/abyss-stack` or `${AOA_SOURCE_ROOT}` with `/srv/abyss-stack`
- do not convert public-safe config templates into committed secret-bearing runtime files
- do not publish rendered config output that may contain secret-bearing values
- do not commit private host-facts captures from live machines
- do not turn `aoa-doctor` into a generic inventory or monitoring program

## Default stance

- prefer minimal reversible changes
- prefer profile-aware module changes over all-stack rewrites
- prefer placeholder or skeletal files over pretending unfinished services are complete
- prefer clarity and explicit boundaries over magical automation
- preserve `/srv/abyss-stack` as the canonical deployed runtime root unless explicitly redesigned
- preserve the split between normative platform docs, public-safe host facts, and private host facts
- treat current-machine fit as a first-class runtime concern before latency-sensitive or accelerator-sensitive work

## Host-facts rule

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
- if paths, ports, or host posture change, re-read the relevant path, deployment, runbook, and reference-platform docs before finishing
- use the narrowest dry-run or public-safe validation available for the changed scripts, modules, or docs

## Review guidelines

For GitHub review in this repository, treat the following as P0:

- committed live secrets or secret-bearing rendered configs
- a change that widens default host exposure beyond localhost without explicit operator intent
- a bootstrap or runtime change that can destroy data without rollback guidance

Treat the following as P1:

- env examples drifting away from actual runtime consumers
- path mapping drift away from `/srv/abyss-stack`, `Configs`, or `Secrets`
- profile/preset/module changes without matching render/introspection verification
- hidden breaking changes in doctor/bootstrap/first-run helpers
- runtime substrate starting to author meaning that belongs in AoA or ToS
- claiming validation that was not actually run

Ignore trivial wording nits unless the task explicitly asks for copyediting.
