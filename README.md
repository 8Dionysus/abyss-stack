# abyss-stack

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem. It is **Fedora-first** in deployment posture while remaining **Windows-usable** for source work, path mapping, and hybrid workflows. It owns runtime, deployment, storage layout, lifecycle, security, reference-platform posture, and infrastructure glue. It does not own the authored meaning of the specialized AoA layers or ToS.

> Current release: `v0.2.2`. See [CHANGELOG](CHANGELOG.md) for release notes.

## Start here

Read in this order:

1. [CHARTER](CHARTER.md)
2. [BOUNDARIES](BOUNDARIES.md)
3. [DESIGN](DESIGN.md)
4. [docs/ARCHITECTURE](docs/ARCHITECTURE.md)
5. [mechanics/README](mechanics/README.md)
6. [docs/SERVICE_CATALOG](docs/SERVICE_CATALOG.md)
7. [docs/PROFILES](docs/PROFILES.md) and [docs/PRESETS](docs/PRESETS.md)
8. [docs/PATHS](docs/PATHS.md)
9. [docs/DEPLOYMENT](docs/DEPLOYMENT.md), [docs/FIRST_RUN](docs/FIRST_RUN.md), [docs/RUNBOOK](docs/RUNBOOK.md), and [docs/SECURITY](docs/SECURITY.md)
10. [ROADMAP](ROADMAP.md)

Then branch by need:

- **Windows host and WSL bridge**: [Windows bridge](mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_BRIDGE.md), [Windows setup](mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_SETUP.md), [Windows performance](mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_PERFORMANCE.md)
- **host posture and machine facts**: [reference platform](mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md), [reference platform spec](mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md), [machine bridge](mechanics/machine-fit/parts/machine-bridge/docs/MACHINE_BRIDGE.md), [machine fit policy](mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md), [platform adaptation policy](mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md)
- **runtime benchmark and local-model posture**: [runtime bench policy](mechanics/inference-pilots/parts/local-trials/docs/RUNTIME_BENCH_POLICY.md), [winner promotion loop](mechanics/inference-pilots/parts/promotion-loop/docs/RUNTIME_WINNER_PROMOTION_LOOP.md), [llama.cpp pilot](mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md), [local AI trials](mechanics/inference-pilots/parts/local-trials/docs/LOCAL_AI_TRIALS.md), [model profiles](mechanics/machine-fit/parts/inference-tuning/docs/MODEL_PROFILES.md), [model cards](mechanics/machine-fit/parts/inference-tuning/docs/MODEL_CARDS.md), [context budget policy](mechanics/governed-execution/parts/local-worker-path/docs/CONTEXT_BUDGET_POLICY.md)
- **branch and recurrence posture**: [branch policy](docs/BRANCH_POLICY.md), [recurrence runtime policy](mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md)
- **runtime-side AoA seams**: [memo runtime seam](mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md), [eval runtime seam](mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md), [playbook runtime seam](mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md), [KAG runtime seam](mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md), [antifragility runtime](mechanics/runtime-repair/parts/antifragility-posture/docs/ANTIFRAGILITY_RUNTIME.md), [runtime repair provenance](mechanics/runtime-repair/PROVENANCE.md), [repair-safe closeout](mechanics/runtime-repair/parts/repair-safe-closeout/docs/REPAIR_SAFE_CLOSEOUT.md), and [diagnostic spine](mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md)
- **runtime-side via negativa posture**: [via negativa checklist](mechanics/runtime-repair/parts/antifragility-posture/docs/VIA_NEGATIVA_CHECKLIST.md)
- **runtime mechanics topology**: [mechanics/README](mechanics/README.md) and [docs/MECHANICS](docs/MECHANICS.md)
- **root route and design surfaces**: [AGENTS](AGENTS.md), [DESIGN](DESIGN.md), and [DESIGN.AGENTS](DESIGN.AGENTS.md)
- **agent overlays and fast-loop lanes**: [.agents](.agents/README.md) and [.agents/spark](.agents/spark/README.md)
- **operator command map**: [scripts/README](scripts/README.md)

## What this repository is for

This repository is the right home for:

- local and hybrid runtime topology
- rootless Podman and systemd user orchestration
- storage and mount contracts
- service modules and deployment profiles
- versioned helper-service build contexts
- security, runbook, backup, and restore posture
- normative host posture and machine-readable host-facts contracts
- read-only `abyss-machine` bridge consumption and runtime-local route indexing
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
- deployed runtime root: `/srv/AbyssOS/abyss-stack`
- deployed config tree: `/srv/AbyssOS/abyss-stack/Configs`
- do not edit `/srv/AbyssOS/abyss-stack` as if it were the source repository

The deployed runtime mirror under `/srv/AbyssOS/abyss-stack/Configs` is intentionally narrower than the source checkout.
Source checkout shape is authoritative in `~/src/abyss-stack`; `/srv/AbyssOS/abyss-stack/Configs` is a deployed runtime mirror for running and inspecting the stack.
The GitHub mirror is source-only: it should carry the docs, templates, schemas,
examples, tests, workflows, and scripts needed to create a runtime, but not live
`Secrets/`, `Logs/`, `Models/`, `stack.env`, rendered config, local databases,
model files, or private captures. Runtime state is created from the checkout
through `scripts/aoa-install-layout`, `scripts/aoa-sync-configs`, and
`scripts/aoa-bootstrap-configs`.

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

`abyss-stack` currently exposes a deployed multi-service runtime substrate with stateful storage, local and Intel-aware inference paths, monitoring, host-facts capture, stack-side `abyss-machine` bridge capture, machine-fit capture, platform-adaptation logging, and landed federation advisory seams for sibling AoA repositories.

The current bounded promoted local-worker posture is `langchain-api` on `5403` backed directly by `llama.cpp`, with `LangGraph` as the adopted execution layer for bounded long-horizon and autonomy-focused local-worker flows. Federation seams remain opt-in, bounded, and explicit: they can enrich runtime behavior when the `federation` profile is active, but they do not replace source-owned meaning and they should not be read as blanket proof of full federated control-plane coherence.
The archived long-horizon and bounded-autonomy pilot contracts now route through
`mechanics/inference-pilots/PROVENANCE.md`; operator entry uses
`scripts/aoa-long-horizon-pilot` and `scripts/aoa-bounded-autonomy-pilot`
rather than keeping old family labels as root command topology.

Antifragility repair posture stays contract-only in this repository. It adds
runtime-side doctrine plus receipt schemas/examples for degradation and
repair-safe closeout without changing live services, scripts, or deployment
behavior.
Current contract surfaces are `mechanics/runtime-repair/parts/antifragility-posture/docs/ANTIFRAGILITY_RUNTIME.md`,
`mechanics/runtime-repair/PROVENANCE.md`,
`mechanics/runtime-repair/parts/repair-safe-closeout/docs/REPAIR_SAFE_CLOSEOUT.md`,
`mechanics/runtime-repair/parts/degradation-receipts/schemas/service-degradation-receipt.schema.json`,
`mechanics/runtime-repair/parts/repair-safe-closeout/schemas/repair-safe-closeout-receipt.schema.json`,
`mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.example.json`, and
`mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.example.json`.
Chaos receipt examples also now include
`mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.timeout-chaos.example.json`,
`mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.honest-degradation.example.json`,
`mechanics/runtime-repair/parts/degradation-receipts/examples/service-degradation-receipt.retrieval-outage-honesty.example.json`,
`mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.timeout-chaos.example.json`, and
`mechanics/runtime-repair/parts/repair-safe-closeout/examples/repair-safe-closeout-receipt.retrieval-outage-honesty.example.json`.

Diagnostic spine groundwork now includes a read-only `aoa-diagnose` seam in
this repository. It adds a runtime-owned diagnostic read model, tracked quest
follow-through, schema/example surfaces, and a bounded artifact writer without
changing live services, deployment behavior, or the readiness-only posture of
`aoa-doctor`.
Current contract surfaces are `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_target.schema.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_session.schema.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnosis_companion.schema.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/diagnostic_anchor_ref.schema.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/repair_handoff.schema.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/schemas/reviewed_diagnosis_ref.schema.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_target.min.example.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_session.min.example.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnosis_companion.min.example.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/diagnostic_anchor_ref.min.example.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/repair_handoff.min.example.json`,
`mechanics/diagnostic-spine/parts/diagnostic-surfaces/examples/reviewed_diagnosis_ref.min.example.json`, and
`quests/diagnostics/captured/ABYSS-STACK-Q-0007.yaml`.
The repo-local Codex adapter surface for this pass is
`.agents/skills/abyss-self-diagnostic-spine`, sourced from `aoa-skills`.
The repo-local bounded `abyss-*` overlay skill surface also includes
`.agents/skills/abyss-safe-infra-change` and
`.agents/skills/abyss-sanitized-share`, both sourced from `aoa-skills` and
kept distinct from the wider shared `aoa-*` install set.
The current read-only runtime seam is `scripts/aoa-diagnose`, backed by
`mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py`. It can now emit `diagnosis_companion.json` and
`repair_handoff.json` on `--write-latest`, write an explicit
`reviewed_diagnosis.ref.json` bridge on `--write-reviewed-diagnosis-ref`,
accept explicit `--with-reviewed-diagnosis-ref` inputs, and refresh
`last_good.ref.json` only through the explicit `--write-last-good-ref` flag.

To verify the current promoted path, use this order:

1. `python scripts/validate_stack.py`
2. `python scripts/build_diagnostic_surface_catalog.py --check`
3. `python scripts/validate_diagnostic_surface_catalog.py`
4. `python scripts/validate_stack.py --parity-check`
5. `python scripts/aoa-machine-bridge --check`
6. `python /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-llamacpp-pilot verify --timeout 60`
7. `bash /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-status --autonomy --json`
8. `bash /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-diagnose --preset intel-full --truth-goal live_available --write-latest`
9. `bash /srv/AbyssOS/abyss-stack/Configs/scripts/aoa-diagnose --preset intel-full --truth-goal live_available --against last-good`
