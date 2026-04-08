# abyss-stack

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem. It is **Fedora-first** in deployment posture while remaining **Windows-usable** for source work, path mapping, and hybrid workflows. It owns runtime, deployment, storage layout, lifecycle, security, reference-platform posture, and infrastructure glue. It does not own the authored meaning of the specialized AoA layers or ToS.

## Start here

Read in this order:

1. [CHARTER](CHARTER.md)
2. [BOUNDARIES](BOUNDARIES.md)
3. [docs/ARCHITECTURE](docs/ARCHITECTURE.md)
4. [docs/SERVICE_CATALOG](docs/SERVICE_CATALOG.md)
5. [docs/PROFILES](docs/PROFILES.md) and [docs/PRESETS](docs/PRESETS.md)
6. [docs/PATHS](docs/PATHS.md)
7. [docs/DEPLOYMENT](docs/DEPLOYMENT.md), [docs/FIRST_RUN](docs/FIRST_RUN.md), [docs/RUNBOOK](docs/RUNBOOK.md), and [docs/SECURITY](docs/SECURITY.md)
8. [ROADMAP](ROADMAP.md)

Then branch by need:

- **Windows host and WSL bridge**: [docs/WINDOWS_BRIDGE](docs/WINDOWS_BRIDGE.md), [docs/WINDOWS_SETUP](docs/WINDOWS_SETUP.md), [docs/WINDOWS_PERFORMANCE](docs/WINDOWS_PERFORMANCE.md)
- **host posture and machine facts**: [docs/REFERENCE_PLATFORM](docs/REFERENCE_PLATFORM.md), [docs/REFERENCE_PLATFORM_SPEC](docs/REFERENCE_PLATFORM_SPEC.md), [docs/MACHINE_FIT_POLICY](docs/MACHINE_FIT_POLICY.md), [docs/PLATFORM_ADAPTATION_POLICY](docs/PLATFORM_ADAPTATION_POLICY.md)
- **runtime benchmark and local-model posture**: [docs/RUNTIME_BENCH_POLICY](docs/RUNTIME_BENCH_POLICY.md), [docs/LLAMACPP_PILOT](docs/LLAMACPP_PILOT.md), [docs/LOCAL_AI_TRIALS](docs/LOCAL_AI_TRIALS.md), [docs/MODEL_PROFILES](docs/MODEL_PROFILES.md), [docs/CONTEXT_BUDGET_POLICY](docs/CONTEXT_BUDGET_POLICY.md)
- **branch and recurrence posture**: [docs/BRANCH_POLICY](docs/BRANCH_POLICY.md), [docs/RECURRENCE_RUNTIME_POLICY](docs/RECURRENCE_RUNTIME_POLICY.md)
- **runtime-side AoA seams**: [docs/MEMO_RUNTIME_SEAM](docs/MEMO_RUNTIME_SEAM.md), [docs/EVAL_RUNTIME_SEAM](docs/EVAL_RUNTIME_SEAM.md), [docs/PLAYBOOK_RUNTIME_SEAM](docs/PLAYBOOK_RUNTIME_SEAM.md), [docs/KAG_RUNTIME_SEAM](docs/KAG_RUNTIME_SEAM.md), [docs/ANTIFRAGILITY_RUNTIME](docs/ANTIFRAGILITY_RUNTIME.md), [docs/REPAIR_SAFE_CLOSEOUT](docs/REPAIR_SAFE_CLOSEOUT.md), and [docs/DIAGNOSTIC_SPINE](docs/DIAGNOSTIC_SPINE.md)
- **runtime-side via negativa posture**: [docs/VIA_NEGATIVA_CHECKLIST](docs/VIA_NEGATIVA_CHECKLIST.md)

## What this repository is for

This repository is the right home for:

- local and hybrid runtime topology
- rootless Podman and systemd user orchestration
- storage and mount contracts
- service modules and deployment profiles
- versioned helper-service build contexts
- security, runbook, backup, and restore posture
- normative host posture and machine-readable host-facts contracts
- current-machine fit policy and bounded machine-local tuning guidance
- platform-adaptation policy and public-safe/private tuning record contracts
- infrastructure helper services that support AoA and ToS

## What this repository is not for

This repository should not absorb:

- technique canon
- skill canon
- eval canon
- routing truth as such
- memo objects as primary truth
- agent role contracts as primary truth
- playbook meaning as primary truth
- ToS authored corpus and philosophical source material
- AoA constitutional truth

## Quick path rule

- source checkout: `~/src/abyss-stack` by default, or `${AOA_SOURCE_ROOT}` if intentionally relocated
- deployed runtime root: `/srv/abyss-stack`
- deployed config tree: `/srv/abyss-stack/Configs`
- do not edit `/srv/abyss-stack` as if it were the source repository

The deployed runtime mirror under `/srv/abyss-stack/Configs` is intentionally narrower than the source checkout.

## Quick route table

| repository | owns | go here when |
|---|---|---|
| `abyss-stack` | runtime, deployment, storage, lifecycle, and infra glue | you need the body the system runs on |
| `Agents-of-Abyss` | ecosystem identity, layer map, federation rules, program-level direction | you need the center and the constitutional view of AoA |
| `Tree-of-Sophia` | living knowledge architecture for philosophy and world thought | you need the knowledge world rather than the runtime body |
| `aoa-techniques` | reusable engineering practice | you need durable techniques rather than infrastructure modules |
| `aoa-kag` | derived retrieval, reasoning-handoff, and regrounding packs | you need KAG-side advisory retrieval surfaces rather than live runtime services |
| `aoa-skills` | bounded agent-facing execution workflows | you need executable workflows rather than deployment posture |
| `aoa-memo` | memory objects, recall contracts, and memo-side writeback meaning | you need memory-layer authority rather than runtime export plumbing |
| `aoa-evals` | portable proof surfaces for bounded claims | you need evaluation and quality checks rather than runtime services |
| `aoa-playbooks` | playbook doctrine, authored execution bundles, and playbook-owned meaning | you need playbook authority rather than runtime advisory mirrors |

## Current posture

`abyss-stack` currently exposes a deployed multi-service runtime substrate with stateful storage, local and Intel-aware inference paths, monitoring, host-facts capture, machine-fit capture, platform-adaptation logging, and landed federation advisory seams for sibling AoA repositories.

The current bounded promoted local-worker posture is `langchain-api` on `5403` backed directly by `llama.cpp`, with `LangGraph` as the adopted execution layer for bounded long-horizon and autonomy-focused local-worker flows. Federation seams remain opt-in, bounded, and explicit: they can enrich runtime behavior when the `federation` profile is active, but they do not replace source-owned meaning and they should not be read as blanket proof of full federated control-plane coherence.

Antifragility wave two stays contract-only in this repository. It adds
runtime-side doctrine plus receipt schemas/examples for degradation and
repair-safe closeout without changing live services, scripts, or deployment
behavior.
Current contract surfaces are `docs/ANTIFRAGILITY_RUNTIME.md`,
`docs/REPAIR_SAFE_CLOSEOUT.md`,
`schemas/service_degradation_receipt_v1.json`,
`schemas/repair_safe_closeout_receipt_v1.json`,
`examples/service_degradation_receipt.example.json`, and
`examples/repair_safe_closeout_receipt.example.json`.

Diagnostic spine groundwork now includes a read-only `aoa-diagnose` seam in
this repository. It adds a runtime-owned diagnostic read model, tracked quest
follow-through, schema/example surfaces, and a bounded artifact writer without
changing live services, deployment behavior, or the readiness-only posture of
`aoa-doctor`.
Current contract surfaces are `docs/DIAGNOSTIC_SPINE.md`,
`schemas/diagnostic_target.schema.json`,
`schemas/diagnostic_session.schema.json`,
`schemas/diagnosis_companion.schema.json`,
`schemas/diagnostic_anchor_ref.schema.json`,
`schemas/repair_handoff.schema.json`,
`schemas/reviewed_diagnosis_ref.schema.json`,
`examples/diagnostic_target.min.example.json`,
`examples/diagnostic_session.min.example.json`,
`examples/diagnosis_companion.min.example.json`,
`examples/diagnostic_anchor_ref.min.example.json`,
`examples/repair_handoff.min.example.json`,
`examples/reviewed_diagnosis_ref.min.example.json`, and
`quests/ABYSS-STACK-Q-0007.yaml`.
The repo-local Codex adapter surface for this pass is
`.agents/skills/abyss-self-diagnostic-spine`, sourced from `aoa-skills`.
The current read-only runtime seam is `scripts/aoa-diagnose`, backed by
`scripts/_aoa_diagnose.py`. It can now emit `diagnosis_companion.json` and
`repair_handoff.json` on `--write-latest`, write an explicit
`reviewed_diagnosis.ref.json` bridge on `--write-reviewed-diagnosis-ref`,
accept explicit `--with-reviewed-diagnosis-ref` inputs, and refresh
`last_good.ref.json` only through the explicit `--write-last-good-ref` flag.

To verify the current promoted path, use this order:

1. `python scripts/validate_stack.py`
2. `python scripts/validate_stack.py --parity-check`
3. `python /srv/abyss-stack/Configs/scripts/aoa-llamacpp-pilot verify --timeout 60`
4. `bash /srv/abyss-stack/Configs/scripts/aoa-status --autonomy --json`
5. `bash /srv/abyss-stack/Configs/scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest`
6. `bash /srv/abyss-stack/Configs/scripts/aoa-diagnose --preset intel-full --truth-goal live_available --against last-good`
