# Changelog

All notable changes to `abyss-stack` will be documented in this file.

The format is intentionally simple and human-first.
Tracking starts with the community-docs baseline for this repository.

## [Unreleased]

### Added

- initial `mechanics/` topology with runtime lifecycle, config projection,
  machine fit, inference pilots, federation seams, governed execution,
  diagnostic spine, and runtime repair package cards
- follow-up `mechanics/agon-runtime` and `mechanics/experience-runtime`
  archive-containment packages with provenance and `legacy/` indexes
- archive-containment bridges for `mechanics/runtime-repair` and
  `mechanics/inference-pilots`, including quiet pilot bridge commands
- stack-side `abyss-machine` bridge capture via `scripts/aoa-machine-bridge`,
  with `Logs/machine-bridge/` latest/history/index routes and package-local
  contract docs
- root `systemd/` route card and README so user-unit skeletons no longer sit
  behind an unowned top-level folder
- `.agents/spark/README.md` as the repo-local route surface for the fast-loop
  lane
- `scripts/README.md` as the stable command map for root wrappers, validators,
  and their mechanic ownership routes
- `docs/README.md` and `tests/README.md` as root district indexes for
  repository docs and repo-level validation
- `.agents/` and `.github/` route README surfaces, plus `.agents/AGENTS.md` for
  repo-local agent overlays
- root `DESIGN.md` and `DESIGN.AGENTS.md` surfaces, adapting the AoA route-card
  pattern to the `abyss-stack` runtime substrate

### Changed

- root `AGENTS.md` now follows the canonical route-card shape and routes future
  passes through runtime design and agent-surface design before local work
- top-level route docs now point runtime-move work through the mechanics atlas
  before entering package-specific docs, scripts, schemas, or config surfaces
- noisy Agon and experience archival artifacts, including late-found experience
  job/worker/storage-plan docs, moved out of flat root districts into
  package-local `legacy/` homes with validators and tests following the move
- runtime repair chaos receipts and preserved pilot files moved out of flat
  root districts into package-local `legacy/` homes with route bridges
- GitHub mirror hygiene now keeps the repository source/install-only by
  ignoring obvious local runtime artifacts and failing validation on tracked
  live/private/heavy files while preserving public examples and fixtures
- part-owned mechanic docs now live under their owning `parts/<part>/docs/`
  homes for config projection, diagnostic spine, governed execution, inference
  pilots, and runtime lifecycle, with validators, tests, quest anchors, and
  generated diagnostic refs following the move
- config-projection and runtime-lifecycle operator commands now keep stable
  root `scripts/` wrappers while their implementation bodies live under the
  owning mechanic parts, with validator and CI shellcheck coverage for the
  wrapper/backend bridge
- remaining root operator commands now follow the same wrapper/backend pattern
  across diagnostic spine, machine fit, inference pilots, federation seams,
  governed execution, runtime lifecycle, runtime repair, and Windows bridge
  surfaces
- `release_check.py` now uses synthetic Configs parity by default, keeping
  source release audits independent from stale live runtime mirrors unless
  `--parity-mode live` is requested
- model-card docs no longer carry host-local source checkout links, and
  `validate_stack.py` now blocks that portability drift while still allowing
  the canonical deployed runtime root references
- the local diagnostic-spine skill overlay now points at current part-local
  diagnostic surfaces, and `validate_stack.py` blocks stale moved mechanic doc
  references
- active mechanics route docs now keep old family labels in provenance,
  contract paths, and bridges instead of package-active prose
- `FIRST_RUN` now routes optional local model trials to inference-pilot and
  machine-fit surfaces instead of spelling the old W0-W4 qualification runner
  as part of normal bootstrap
- `aoa-local-ai-trials` now keeps its preserved W0-W4 runner under
  `mechanics/inference-pilots/legacy/artifacts/scripts/` with a thin active
  compatibility bridge in `parts/local-trials/`
- root residual route surfaces were tightened: the audit contract now lives at
  `docs/AUDIT.md`, the Spark fast-loop lane lives under `.agents/spark/`, and
  validators block those root-level residual paths from returning

## [0.2.2] - 2026-04-23

### Summary

- this patch lands Agon duel-kernel runtime records, event-log models,
  mechanical-trial run registries, and hash-chain quest surfaces while keeping
  those records bounded to runtime-owned infrastructure truth
- Experience watchtower, certification/deployment storage, federation harvest,
  adoption worker, retention, rollback, KAG promotion, pattern registry, and
  assistant release-lifecycle stack contracts are added for the current release
  line
- `abyss-stack` remains the source-authored runtime layer; deployed state
  still becomes live only through the configured runtime mirror and operator
  process

### Added

- Agon Wave XII duel runtime kernel surfaces, duel event logs, stop-lines,
  registry generation, and source/deployed recurrence manifests
- Agon Wave XIII mechanical-trial runtime records, event-log examples,
  trial-run registries, and runtime stop-lines
- Experience watchtower runtime records plus wave3 federation/adoption worker
  plans, runtime storage plans, canary probes, rollback jobs, KAG promotion
  jobs, and pattern-registry service records

### Changed

- runtime review follow-up drift, event-log schema checks, mechanical-trial
  contract checks, long-horizon pilot record posture, federation runtime review
  contracts, and source/deployed parity expectations were tightened

### Validation

- `python scripts/release_check.py`

### Notes

- this patch updates source-owned runtime contracts and public-safe docs only;
  it does not claim live deployment mutation from the source checkout

## [0.2.1] - 2026-04-19

### Summary

- this patch adds chaos-wave runtime recovery, memo contradiction sidecars,
  and A2A return dry-run adapters across the runtime layer
- federated-consumer warnings, release parity CI, and roadmap/current-direction
  docs are tightened around the current runtime contour
- `abyss-stack` remains the source-owned runtime layer, with deployed truth
  still landing through the `Configs` mirror

### Added

- runtime chaos recovery surfaces, an A2A return closeout dry-run
  adapter, and memo contradiction runtime-sidecar coverage

### Changed

- federated-consumer warning posture, recall/contradiction bridge wiring,
  release parity CI safety, and CI/protection surfaces are aligned with the
  current runtime release line

### Validation

- `python scripts/release_check.py`

### Notes

- this patch extends bounded runtime recovery and advisory posture without
  claiming live deployment mutation from the source repository alone

## [0.2.0] - 2026-04-10

### Summary

- this release adds diagnostic-spine contracts, source-rooted mirror canaries, federated advisory seams, winner-promotion loops, and new OVMS/chat/ToS-graph runtime lanes
- llama.cpp fallback and tuning posture are hardened while runtime docs and AGENTS guidance are aligned around parity, support boundaries, and bounded advisory ownership
- `abyss-stack` remains source-authored on the runtime layer, with deployed state becoming live only after sync into the `Configs` mirror

### Validation

- `python scripts/release_check.py`

### Notes

- detailed runtime substrate, generated-surface, operator-surface, and parity-check coverage for this release remains enumerated below under `Added`, `Changed`, and `Included in this release`

### Added

- diagnostic-spine runtime seam, diagnostic surface-catalog capsule,
  reviewed-diagnosis bridge refs, and repair-handoff companion alignment
- source-rooted mirror canary plus parity-aware deployment verification for
  the deployed `Configs` mirror
- federated advisory seam presets and live checks, overlay skill installs,
  runtime winner-promotion loop, and checkpoint closeout bridge install in the
  repo skill surface
- Intel OVMS text-lab lane, Qwen3/OVMS model cards, route-first ToS-graph UI,
  preview-only curation slice, and a generic runtime chat seam

### Changed

- added llama.cpp runtime fallback for AVX512-less hosts and hardened
  llama.cpp env compatibility and tuning seams
- aligned runtime docs and AGENTS guidance with current support posture, via
  negativa runtime checks, and bounded advisory/runtime ownership

### Included in this release

- runtime substrate updates across `compose/`, `config-templates/`, `docs/`,
  `examples/`, `schemas/`, `scripts/`, and `generated/`, including the switch
  to canonical llama.cpp posture, diagnostic-spine contracts, antifragility
  receipt schemas, machine-fit fallback and tuning, and federated advisory
  seams
- runtime follow-through and operator surfaces under `.agents/`, `.github/`,
  `docs/AUDIT.md`, `ROADMAP.md`, `QUESTBOOK.md`, `quests/`, `README.md`,
  `AGENTS.md`, `.agents/spark/`, and `tests/`, including quest-harvest installs,
  runtime closeout receipts, winner promotion, route-first ToS graph UI and
  curation overlays, OVMS text-lab lanes, and parity-safe source and deployed
  mirror checks

## [0.1.0] - 2026-04-01

First public baseline release of `abyss-stack` as the infrastructure substrate for the AoA / ToS ecosystem.

This changelog entry uses the release-prep merge date.

### Summary

- first public baseline release of `abyss-stack` as the repository that owns runtime, deployment, storage, lifecycle, security, and infrastructure glue beneath AoA and ToS
- the public baseline now includes Fedora-first deployment doctrine, source-checkout versus deployed-runtime path rules, rootless Podman lifecycle helpers, profile and preset composition, helper-service build contexts, and bounded federation/runtime seams
- this release keeps `abyss-stack` on the runtime layer without absorbing source-owned meaning from AoA layers or `Tree-of-Sophia`

### Added

- community-docs baseline established for this repository
- `CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, and `CONTRIBUTING.md`
- root runtime doctrine under `README.md`, `CHARTER.md`, `BOUNDARIES.md`, `ROADMAP.md`, and the current `docs/` architecture, deployment, runbook, path, preset, profile, reference-platform, machine-fit, and runtime-bench surfaces
- source-managed runtime helpers under `scripts/`, including layout, sync, bootstrap, lifecycle, doctor, render-truth, smoke, governed-run, host-facts, machine-fit, pilot, and federation-sync entrypoints
- public-safe config templates, helper-service contexts, schemas, and examples under `config-templates/`, `schemas/`, and `examples/`

### Validation

- `python scripts/validate_stack.py`
- `python scripts/validate_stack.py --parity-check`
- `python -m py_compile scripts/validate_stack.py scripts/aoa-host-facts scripts/aoa-machine-fit scripts/aoa-qwen-run`

### Notes

- this release establishes the source-authored baseline for the runtime layer; deployed runtime state still becomes live only after sync into `/srv/AbyssOS/abyss-stack/Configs`
