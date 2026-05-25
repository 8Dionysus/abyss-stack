# Changelog

All notable changes to `abyss-stack` will be documented in this file.

The format is intentionally simple and human-first.
Tracking starts with the community-docs baseline for this repository.

## [Unreleased]

### Summary

- root direction, release history, and decision rationale now follow an
  explicit AoA-style role split adapted to the `abyss-stack` runtime substrate
- root `README.md` is now a compact source-checkout front door instead of a
  current-state inventory or package-local surface ledger
- decision records are now validator-backed and indexed as durable rationale,
  not remembered as a loose convention from previous refactor passes
- root `ROADMAP.md` is now a runtime-wide horizon surface instead of a mixed
  landing history, backlog, and release-contour document
- root `docs/` now uses role-named districts instead of a flat surface list,
  preserving the AbyssOS source/runtime split in the folder topology itself
- the Intel workstation route now has explicit service-selection docs, a Gemma
  4 E2B `llama.cpp` Vulkan lane, an opt-in Qwen3 rerank API profile, thin-host
  guard overlays, a protected TTS keep-warm timer, and the first source-linked
  RAG orchestration profile

### Added

- `docs/decisions/AGENTS.md`, `docs/decisions/TEMPLATE.md`,
  `scripts/validate_decision_records.py`, and `tests/test_decision_records.py`
  as the local decision-record contract and validation lane
- `docs/decisions/2026-05-14-direction-history-decision-surface-roles.md` as
  the rationale for the `ROADMAP.md`, `CHANGELOG.md`, and `docs/decisions/`
  role split
- `docs/routes/START_HERE_ROUTE_CONTRACT.md` as the source-checkout route-mode
  contract for root entry surfaces
- `docs/{routes,runtime,install,operations,profiles,governance,legacy}/README.md`
  as short district maps for repo-wide documentation
- `docs/decisions/2026-05-14-docs-district-topology.md` as the rationale for
  the docs district split
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
- `.agents/` route README and `.github/GITHUB_SURFACE.md`, plus
  `.agents/AGENTS.md` for repo-local agent overlays and GitHub-native route
  mapping that does not compete with the homepage README
- root `DESIGN.md` and `DESIGN.AGENTS.md` surfaces, adapting the AoA route-card
  pattern to the `abyss-stack` runtime substrate
- `mcp/services/AGENTS.md`, `mcp/services/README.md`, and
  `docs/decisions/2026-05-20-mcp-services-topology.md` as the canonical MCP
  service-package topology for `aoa-memo-mcp`
- `mcp/services/abyss-machine-mcp/` and
  `docs/decisions/2026-05-25-abyss-machine-mcp-access-plane.md` as the
  stack-owned, read-only MCP access plane over `abyss-machine` host read models
- `docs/runtime/SERVICE_SELECTION.md` as the source-level service-selection
  guide for lean Intel, full Intel, optional workflows, tools, observability,
  reranking, and protected speech routes
- `compose/modules/45-rerank-api.yml`, `compose/profiles/reranking.txt`, and
  `config-templates/Services/rerank-api/` for the explicit localhost-only
  OpenVINO Qwen3 reranker wrapper
- `compose/modules/46-rag-api.yml`, `compose/profiles/rag.txt`,
  `compose/tuning/rag.thin-host.yml`,
  `config-templates/Configs/rag/`, and
  `config-templates/Services/rag-api/` for the first lightweight RAG,
  Agentic-RAG trace, and DAG manifest orchestration layer over existing stack
  services
- `compose/tuning/llamacpp.gemma4-e2b.intel-285h.vulkan.yml` for the candidate
  Gemma 4 E2B text lane on the Intel 285H class through `llama.cpp` Vulkan
- `compose/tuning/storage.intel-285h.resource-guard.yml`,
  `compose/tuning/observability.thin-host.yml`,
  `compose/tuning/tools.thin-host.yml`, and
  `compose/tuning/workflows.thin-host.yml` as explicit resource guard overlays
  for selected services
- `systemd/user/abyss-tts-keepwarm.service` and
  `systemd/user/abyss-tts-keepwarm.timer` for bounded TTS warmth through the
  existing protected host TTS server
- `docs/decisions/2026-05-15-intel-inference-and-rerank-service-selection.md`
  as the rationale for the current Gemma, OVMS embeddings, Qwen3 reranking,
  protected TTS, and optional-service split

### Changed

- `aoa-evals-mcp` now treats explicit `runtime-candidate-export:<id>` refs as
  strict runtime export selectors and filters weak route tokens, preventing
  unrelated runtime candidate exports from being attached to eval-need
  proposals.
- root `AGENTS.md` now follows the canonical route-card shape and routes future
  passes through runtime design and agent-surface design before local work
- top-level route docs now point runtime-move work through the mechanics atlas
  before entering package-specific docs, scripts, schemas, or config surfaces
- flat root docs moved into role-named districts: route contracts under
  `docs/routes/`, runtime topology under `docs/runtime/`, source install under
  `docs/install/`, operations under `docs/operations/`, profile selection under
  `docs/profiles/`, governance under `docs/governance/`, and preserved old
  references under `docs/legacy/`
- source-managed runtime component references now use current inspected
  `version-tag@sha256` pins across storage, orchestration, inference,
  monitoring, and helper service bases, while stateful datastores stay on their
  current compatible lines unless a separate migration packet promotes a major
  jump
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
- quests now use lane/state source topology under `quests/<lane>/<state>/`,
  with public-safe catalog and dispatch examples generated from owner-local
  quest helpers instead of flat root quest files
- `FIRST_RUN` now routes optional local model trials to inference-pilot and
  machine-fit surfaces instead of spelling the old qualification runner
  as part of normal bootstrap
- `aoa-local-ai-trials` now keeps its preserved local-trials runner under
  `mechanics/inference-pilots/legacy/trials/artifacts/scripts/` with active
  compatibility bridge and role-level adapter surfaces in `parts/local-trials/`
- root residual route surfaces were tightened: the audit contract now lives at
  `docs/routes/AUDIT.md`, the Spark fast-loop lane lives under `.agents/spark/`, and
  validators block those root-level residual paths from returning
- LangGraph and llama.cpp promotion surfaces now treat preserved runtime/edit
  gate IDs as compatibility wire IDs behind role-level adapter names, with a
  validator guard against archived stage prose returning
- federation seams now keep upstream eval and playbook compatibility names in
  `parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md` while active route
  docs use clean local route names
- autonomy status now routes preserved long-horizon and bounded-autonomy
  artifact names through explicit index constants
- active workspace sibling defaults and repo-local skill symlinks now route
  through `/srv/AbyssOS/<repo>`, with validation blocking stale active
  `/srv/<repo>` sibling roots outside legacy archives
- Agon dry-run runtime kernels now live as an active
  `mechanics/agon-runtime/parts/runtime-kernels/` substrate with quiet
  definitions, validators, tests, examples, schemas, generated registries, and
  recurrence observation manifests; experience-runtime records remain
  archive-only with an explicit distillation stop-line
- runtime compatibility names are now isolated behind explicit upstream
  contract fields and compatibility maps for eval templates, memo contradiction
  sidecar inputs, A2A return dry-runs, playbook automation plans, and Dionysus
  RPG prep-pack handoffs
- upstream compatibility IDs now flow through
  `Configs/federation/upstream-compatibility-bridge.json` instead of being
  repeated in route-api, exporter, repair, layout, and federation config
  surfaces
- inference-pilot trial compatibility now uses the quiet active bridge
  `parts/local-trials/trial_compatibility_bridge.py`, and the LangGraph
  dependency manifest lives in `parts/langgraph-pilot/requirements.txt`
  instead of the root command-wrapper directory
- all mechanics packages now carry the full package-card layer
  `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and `LANDING_LOG.md`, with
  `validate_stack.py` enforcing the shared card spine
- residual quest frontier state now closes the profile machine-fit packet,
  machine-fit follow-through packet, RPG runtime materialization packet, and
  diagnostic runtime packet while preserving lane-local `done/` records; the
  route-api health and closure stop-line is now also recorded as a closed
  operator-gated live runtime cutover repair
- `aoa-install-systemd` now supports durable host-local runtime selection
  drop-ins with `--preset`, `--profile`, and `--restart-now`; the live
  federation repair preserves `intel-full` and layers `federation` instead of
  narrowing the machine to a federation-only preset
- root `ROADMAP.md` now has explicit authority, update rules, runtime horizons,
  stronger-surface routing, and future triggers so it no longer carries
  mechanic-local landing history or release history as roadmap law
- root `README.md` now routes by entry need, claim type, mechanics package, and
  technical district while sending detailed current state to `ROADMAP.md`,
  `CHANGELOG.md`, `docs/decisions/`, mechanic packages, and `docs/operations/RUNBOOK.md`
- root `README.md` now points validation readers to the broad release gate and
  local command authority surfaces instead of carrying package-specific command
  blocks
- `CHANGELOG.md` now records this role split as release-visible history instead
  of carrying the rationale itself
- all existing decision records now use the standard `Status`, `Date`,
  `Options considered`, `Rationale`, `Source surfaces`, and `Follow-up route`
  shape, with `scripts/release_check.py` running the decision validator before
  the wider release audit
- `aoa-doctor`, `aoa-status --autonomy`, and `aoa-diagnose` now keep the
  machine bridge honest after the docs refactor: source-root detection uses
  `docs/install/DEPLOYMENT.md`, and doctor warns on stale or host-mismatched
  machine-fit and machine-bridge records
- n8n workflow automation now lives behind an explicit `workflows` profile;
  `substrate` and current presets stay workflows-free until a later operator
  decision promotes or retires that layer
- the source-owned default runtime profile is now `substrate`, containing
  storage only, while `local-worker` carries the canonical
  `llama.cpp` plus `langchain-api` worker layer and `core` remains a
  compatibility bundle
- root docs, profile docs, CI rehearsal, the checked-in user-unit skeleton, and
  validation now preserve the split between working substrate, local-worker,
  and richer live runtime selections
- retained Ollama and LiteLLM modules now route through an explicit
  `fallback-gateway` profile, while module/profile README surfaces classify
  substrate, workflow, worker, fallback, projection, helper, visibility, and
  pilot rings
- active render, diagnostic, curation, and machine-fit packet examples now use
  `substrate`, `local-worker`, `fallback-gateway`, or explicit presets instead
  of teaching `core` as the default runtime base
- `aoa-warmup` is now profile-aware across local-worker and fallback modules:
  `llama.cpp` can warm by default, while retained Ollama warmup requires
  explicit `AOA_OLLAMA_WARMUP_ENABLED=true`
- named presets now expand through explicit `substrate + local-worker` or
  `substrate + intel-worker` layers, while broad `agentic` and `intel` profiles
  remain compatibility routes instead of hidden preset bases
- `aoa-machine-fit` now resolves preset membership from the source checkout
  before falling back to deployed `Configs`, so stale live mirrors remain parity
  drift instead of changing the source-owned runtime recommendation
- source-managed systemd unit skeletons now have explicit user and privileged
  support allowlists, with install routes that link or copy units without
  starting, stopping, enabling, disabling, masking, or restarting services
- profile endpoint rendering, smoke probes, validation, profile docs, runtime
  storage docs, and model cards now know about the `reranking` add-on and the
  dedicated `rerank-api` service
- `rerank-api` now has configurable idle unload
  (`AOA_RERANK_IDLE_UNLOAD_SEC`, default `900`) plus a localhost
  `POST /admin/unload` route so occasional reranking does not keep the
  OpenVINO reranker resident forever
- `rerank-api` can exit after idle unload
  (`AOA_RERANK_EXIT_AFTER_IDLE_UNLOAD=true`) so container restart returns
  allocator-held OpenVINO memory to the host instead of relying only on
  in-process object deletion
- `aoa-llamacpp-pilot` can capture a lightweight live tuning snapshot packet
  from an existing `llama.cpp` service without starting or stopping services
- source-managed systemd unit skeletons now use normalized `file:///`
  documentation links, and the automatic power-profile support unit routes
  through the bounded `abyss-machine mode reconcile --light` command
- `abyss-nervous-semantic-maintain.timer` no longer uses `OnActiveSec=10min`,
  so user systemd reloads do not create an extra near-term semantic rebuild
  trigger outside the intended boot and 90-minute cadence
- host-local source-checkout validation now matches only the exact
  `/home/<user>/src/abyss-stack` path segment, avoiding false positives for
  sibling paths such as `abyss-stack-docs`
- the memory MCP access plane now lives under
  `mcp/services/aoa-memo-mcp/`, with route cards, validators, local memo
  receipts, and sibling memory-port references following the canonical service
  path

### Validation

- `python scripts/validate_decision_records.py`
- `python scripts/validate_stack.py`
- `python scripts/validate_nested_agents.py`
- `python -m pytest tests/test_decision_records.py tests/test_roadmap_parity.py`
- `python -m pytest -q`
- `python scripts/release_check.py`
- `systemd-analyze --user verify systemd/user/*.service systemd/user/*.timer systemd/user/*.path`
- `systemd-analyze verify systemd/system/*.service systemd/system/*.timer`
- `scripts/aoa-smoke --profile substrate --profile intel-worker --profile federation --profile reranking`

### Notes

- this pass changes source-owned docs, validators, and tests only; it does not
  mutate live `/srv/AbyssOS/abyss-stack` runtime state or private machine state

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
- Experience watchtower runtime records plus archived federation/adoption worker
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

- this patch adds archived chaos runtime recovery, memo contradiction sidecars,
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
  `docs/routes/AUDIT.md`, `ROADMAP.md`, `QUESTBOOK.md`, `quests/`, `README.md`,
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
