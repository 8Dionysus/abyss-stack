# Changelog

All notable changes to `abyss-stack` will be documented in this file.

The format is intentionally simple and human-first.
Tracking starts with the community-docs baseline for this repository.

## [Unreleased]

## [0.2.1] - 2026-04-19

### Summary

- this patch adds chaos-wave runtime recovery, memo contradiction sidecars,
  and A2A return dry-run adapters across the runtime layer
- federated-consumer warnings, release parity CI, and roadmap/current-direction
  docs are tightened around the current runtime contour
- `abyss-stack` remains the source-owned runtime layer, with deployed truth
  still landing through the `Configs` mirror

### Added

- chaos wave 1 runtime recovery surfaces, an A2A return closeout dry-run
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
  `AUDIT.md`, `ROADMAP.md`, `QUESTBOOK.md`, `quests/`, `README.md`,
  `AGENTS.md`, `Spark/`, and `tests/`, including quest-harvest installs,
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

- this release establishes the source-authored baseline for the runtime layer; deployed runtime state still becomes live only after sync into `/srv/abyss-stack/Configs`
