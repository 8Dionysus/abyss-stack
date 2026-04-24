# ROADMAP

## Current posture

The bootstrap-to-federation landing path is largely complete.
Phases 0 through 6 have already been landed as source and runtime seams:

- modular runtime bootstrap
- service extraction and profile-aware lifecycle wrappers
- Intel-aware and Windows-usable hardening
- `aoa-agents`, `aoa-routing`, `aoa-memo`, `aoa-evals`, `aoa-playbooks`, and `aoa-kag` advisory/read-export landings
- `Tree-of-Sophia` source-owned handoff companion landing
- bounded promoted local-worker posture through `langchain-api` on `5403`
  backed by `llama.cpp`, with `LangGraph` as the adopted execution layer for
  bounded long-horizon and autonomy-focused local-worker flows
- antifragility wave two as contract-only runtime doctrine and receipt
  surfaces, now including bounded wave-one chaos example families, without
  mutating live services or deployment behavior
- read-only diagnostic spine groundwork through `scripts/aoa-diagnose` and
  `generated/diagnostic_surface_catalog.min.json`, still weaker than repair
  authority and live-service mutation

### Current release contour

The live `v0.2.2` contour is runtime-substrate hardening, not a new source of
AoA or ToS meaning. Its current checked surface is:

- source/deployed split and parity posture:
  `README.md`, `CHARTER.md`, `BOUNDARIES.md`, `docs/PATHS.md`,
  `docs/DEPLOYMENT.md`, `scripts/aoa-sync-configs`,
  `scripts/validate_stack.py`, and `scripts/release_check.py`
- diagnostic spine and repair-safe handoff contracts:
  `docs/DIAGNOSTIC_SPINE.md`,
  `generated/diagnostic_surface_catalog.min.json`,
  `schemas/diagnostic_target.schema.json`,
  `schemas/diagnostic_session.schema.json`,
  `schemas/diagnosis_companion.schema.json`,
  `schemas/reviewed_diagnosis_ref.schema.json`,
  `schemas/repair_handoff.schema.json`,
  `examples/diagnostic_target.min.example.json`,
  `examples/diagnostic_session.min.example.json`,
  `examples/diagnosis_companion.min.example.json`,
  `examples/reviewed_diagnosis_ref.min.example.json`,
  `examples/repair_handoff.min.example.json`,
  `scripts/aoa-diagnose`, `scripts/_aoa_diagnose.py`,
  `scripts/build_diagnostic_surface_catalog.py`,
  `scripts/validate_diagnostic_surface_catalog.py`,
  `tests/test_validate_stack_diagnostic_spine.py`, and
  `tests/test_diagnostic_spine_contracts.py`
- antifragility contract-only runtime receipts:
  `docs/ANTIFRAGILITY_RUNTIME.md`, `docs/RUNTIME_CHAOS_WAVE1.md`,
  `docs/REPAIR_SAFE_CLOSEOUT.md`,
  `schemas/service_degradation_receipt_v1.json`,
  `schemas/repair_safe_closeout_receipt_v1.json`,
  `examples/service_degradation_receipt.example.json`,
  `examples/service_degradation_receipt.timeout-chaos.example.json`,
  `examples/service_degradation_receipt.honest-degradation.example.json`,
  `examples/service_degradation_receipt.retrieval-outage-honesty.example.json`,
  `examples/repair_safe_closeout_receipt.example.json`,
  `examples/repair_safe_closeout_receipt.timeout-chaos.example.json`, and
  `examples/repair_safe_closeout_receipt.retrieval-outage-honesty.example.json`
- promoted local-worker and Intel serving posture:
  `docs/RUNTIME_WINNER_PROMOTION_LOOP.md`, `docs/LLAMACPP_PILOT.md`,
  `docs/MACHINE_FIT_POLICY.md`,
  `compose/tuning/llamacpp.runtime-fallback.yml`,
  `compose/tuning/llamacpp.intel-285h.cpu-safe.yml`,
  `compose/tuning/intel-text.ovms-qwen3-settings.yml`,
  `docs/model-cards/qwen3-openvino-family.md`, and
  `scripts/aoa-llamacpp-pilot`
- bounded federation, runtime-chat, and ToS graph curation seams:
  `docs/MEMO_RUNTIME_SEAM.md`, `docs/EVAL_RUNTIME_SEAM.md`,
  `docs/PLAYBOOK_RUNTIME_SEAM.md`, `docs/KAG_RUNTIME_SEAM.md`,
  `docs/SERVICE_CATALOG.md`, `docs/PROFILES.md`,
  `docs/TOS_GRAPH_CURATION.md`, `scripts/aoa-federated-check`,
  `compose/modules/52-tos-graph.yml`, `compose/profiles/curation.txt`, and
  `config-templates/Services/tos-graph/app/main.py`

This contour keeps the source checkout `~/src/abyss-stack` separate from the
deployed `/srv/abyss-stack/Configs` mirror. It names runtime contracts,
advisory seams, and validation paths without claiming live service mutation or
meaning-layer authority.

The main remaining work is live runtime-loop consumption, operational cutover choices, platform hardening, and keeping deployed/runtime truth aligned with source-authored posture.

Those landings should be read carefully:

- landed seams in source and deployed mirrors are not the same thing as a fully green federated control-plane verdict
- the `federation` profile remains opt-in rather than part of the default promoted presets
- current operator truth still depends on parity, promoted runtime verify, and `aoa-status --autonomy --json`

## Phase 0: structured bootstrap

- establish repository charter and boundaries
- create modular compose skeleton
- define first runtime profiles
- define env and secrets posture
- write migration notes from `abyss-stack_old`

## Phase 1: service extraction

- reintroduce storage services cleanly
- reintroduce orchestration and local inference
- reintroduce gateway and agent API modules
- reintroduce speech, browser, and monitoring modules

## Phase 2: operational hardening

- add smoke and health routines
- add profile-aware lifecycle wrappers
- add backup and restore helpers
- add validation for compose coherence
- reduce environment-specific assumptions where possible
- enforce the new `/srv/abyss-stack` canonical runtime root
- make the Fedora-first and Windows-usable path model explicit
- make deployment from source checkout to runtime tree explicit and repeatable

## Phase 3: hybrid growth

- clarify local versus hybrid execution paths
- refine Intel and OVMS posture
- define clean bridges to sibling AoA repositories

## Phase 4: mature substrate

- keep the stack legible under growth
- resist monolith relapse
- let new capability arrive as modules and profiles rather than as hidden sprawl

## Phase 5: live runtime consumption

- decide which federation seams remain advisory-only and which become part of the live loop
- introduce bounded recall, playbook, eval, and KAG consumption in explicit steps
- preserve source-owned authority while adding runtime utility

## Phase 6: platform and operations hardening

- keep runtime cleanup repeatable and legible
- validate reboot and cold-start behavior
- tighten runtime-secret hygiene and stateful-data discipline
- keep Windows and Fedora rollout paths aligned with the same operational model
