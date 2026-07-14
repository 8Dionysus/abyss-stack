# Changelog

All notable changes to `abyss-stack` will be documented in this file.

The format is intentionally simple and human-first.
Tracking starts with the community-docs baseline for this repository.

## [Unreleased]

### Added

- Stack-owned MCP packages now retain portable stdio defaults while supporting
  explicit authenticated loopback shared Streamable HTTP owners on stable
  per-package ports, with source-owned systemd credential/template/bundle
  lifecycle and per-owner canary boundaries.
- Configs sync now supports non-mutating `--dry-run` previews and repeatable
  allowlisted `--item` selection while excluding source-control, bytecode, and
  test/tool cache residue from deployed runtime mirrors.
- A root `stats/` port now declares the live-capable, declaration-only selected
  service running-coverage question, while the service-selection readout keeps
  failed observation distinct from an observed zero and exposes the ratio over
  the full `selected_now` population.
- Repo-self KAG bundles can now be verified and materialized into atomic
  SQLite/FTS, versioned Qdrant, and versioned Neo4j runtime projections with a
  shared current receipt and source-return identities; owner-aware FTS and
  Qdrant filters are indexed, and new vector projections reuse unchanged
  embeddings before processing their document delta.
- `aoa-evals-mcp` now consumes the `aoa-evals` local-port inventory v2 read
  model, exposing source-contract-ready, stale, invalid, or absent local suite
  execution posture without running suite commands or widening the local-port
  write allowlist; v1 and unknown inputs fail closed to `absent`.
- `aoa-kag-mcp` now exposes each provider's source, entity, artifact, and event
  index family plus optional owner-native domain index catalogs through bounded
  read-only tools, resources, and CLI routes.

### Changed

- Validation and test commands now route through active `AGENTS.md` cards,
  command-owner docs, and the canonical lane manifest instead of being copied
  into decision records, landing logs, or the root audit contract; the dated
  service-optimization completion report and its systemd documentation link
  were removed after its durable routes had owners.

### Fixed

- The repo-local `abyss-self-diagnostic-spine` overlay now carries valid
  trigger metadata and the current canonical `aoa-skills` source path, while
  the skill-projection validator rejects missing descriptions, stale canonical
  routes, and legacy top-level frontmatter before Codex startup.
- `aoa-session-memory-mcp` now publishes and validates exact closed-world
  read-only annotations for every tool, allowing Codex approval policy to
  distinguish evidence reads from side-effecting MCP calls without a per-tool
  approval bypass.
- Shared MCP HTTP startup now fails closed without a valid host-local bearer;
  Codex receives only the named environment route, systemd loads the secret as
  a credential, and provisioning rejects symlinked secret paths without
  changing permissions on an existing shared secret root.
- `aoa-session-memory-mcp` transport preflight now recognizes fresh or stale
  loopback shared owners, rejects remote, credential-bearing, and malformed
  HTTP endpoints without crashing, and does not require a per-Codex child for
  a configured shared owner.
- User-unit installation preserves existing `/dev/null` masks instead of
  replacing an operator-disabled unit while linking the managed allowlist.
- Decision graph freshness now distinguishes local cache parity from checkout
  source posture, preserves lag/dirty warnings, and no longer treats arbitrary
  worktree directory names as separate repositories.
- Source-to-Configs sync and parity now include stack-owned `mcp/` packages and
  root `schemas/`, so deployed MCP services cannot silently remain older than
  their merged source packages.
- The `aoa-stats` live-refresh user-unit adapter now watches only the six
  currently admitted owner-local receipt surfaces and delegates registry
  selection to the deployed `aoa-stats` refresh command instead of pinning the
  retired runtime-wave receipt and a sibling-internal registry path.
- `aoa-session-memory-mcp` now preserves producer-classified structured skill
  selection/load candidates and session-qualified task-episode refs across
  compact audit, usage-chain, and dossier packets, while keeping `loaded`
  distinct from skill reads, procedure execution, completion, and
  effectiveness; bounded action summaries retain stronger semantic buckets
  before weak mention, cooccurrence, or context buckets.
- `aoa-session-memory-mcp` compact skill audit, usage-chain, neighborhood, and
  dossier packets now preserve producer-owned candidate states, action
  semantics, evidence refs, and separately bounded rejected foreign
  correlations without exposing raw transcript bodies or claiming a skill
  invocation/effectiveness verdict.
- `aoa-session-memory-mcp` now exposes a read-only transport preflight route
  and CLI command, so agents can distinguish stale/missing Codex MCP transport
  from broken `.aoa` indexes when direct tool calls return `Transport closed`.
- `aoa-session-memory-mcp` now auto-reloads its `core.py` implementation for
  existing tools and reports already-running stale Codex MCP transports in the
  service validator, so freshness/provider packet fixes do not silently depend
  on manual process restarts.
- `aoa-session-memory-mcp` entity usage audit and neighborhood routes now
  return bounded MCP payloads by default, with compact samples, omitted counts,
  freshness summaries, and a full-evidence expansion command instead of dumping
  bulk archive events into agent context.
- `aoa-session-memory-mcp` now exposes a read-only projection-status route over
  the latest `.aoa projection-catchup` completeness diagnostic, so agents can
  see post-classifier/schema projection coverage without running maintenance
  through MCP.
- `aoa-session-memory-mcp` compact status now preserves the latest
  search-shard materialization timings and bounded slow-session samples, so
  agents can see which real session made maintenance slow without opening the
  full `.aoa` report.
- `aoa-session-memory-mcp` compact status now preserves `.aoa` search-shard
  raw-text fallback dependency signals, including blocked shard counts and
  scoped full-text expansion commands, so agents can choose the right bounded
  search route without loading the full maintenance packet.
- `aoa-session-memory-mcp` entity inventory responses now stay bounded for
  wide skill/MCP/hook/tool/API route probes by returning compact sample refs,
  a route packet, sample budget/omitted counts, and an explicit expansion
  command instead of heavy atlas entry paths in every sample.
- Runtime config artifact validation now promotes release-ready evidence through
  the OS Abyss registry, materializes subject-store evidence under ignored
  `dist/`, requires source/trust-root matching and a fail-closed runtime
  trust-gate allow verdict before exposing a latest bundle read-model, and
  makes the manifest declare subject-store admission before runtime consumers
  can use the bundle.
- Release validation now renders the public-safe `substrate` config as an OS
  Abyss artifact bundle and verifies ABI, SBOM, SLSA/in-toto, and
  signature-decision sidecars through `abyss-machine`.
- `aoa-session-memory-mcp` now rejects unsupported retrieval recipes before
  dispatching to the archive, keeping the MCP retrieval allowlist as the local
  gate instead of relying on downstream archive errors.
- `aoa-memo-mcp` now checks colon-suffixed local payload refs like
  `README.md:12` as local paths instead of letting `urlparse` classify them as
  symbolic URI schemes.
- Decision graph builder and `aoa-decisions-mcp` now derive the default
  `abyss-stack` checkout from the running source tree instead of a private
  `/home/dionysus/src/abyss-stack` path.
- `aoa-memo-mcp` now rebuilds the containing local memo port index after
  rejected reviewed-intake receipts, keeping receipt indexes fresh for invalid
  or mismatched export repos.
- `aoa-memo-mcp` briefs now honor read-only workspace memory routes even when a
  physical memo port exists, avoiding candidate-write guidance that the tool
  will reject.

## [0.4.0] - 2026-06-07

### Summary

- root direction, release history, and decision rationale now follow an
  explicit AoA-style role split adapted to the `abyss-stack` runtime substrate
- root `README.md` is now a compact source-checkout front door instead of a
  current-state inventory or package-local surface ledger
- decision records are now validator-backed and indexed as durable rationale,
  not remembered as a loose convention from previous refactor passes
- validation, script, and test topology now have explicit command authority,
  inventories, and lane guards before the large stack validator is split
- root `ROADMAP.md` is now a runtime-wide horizon surface instead of a mixed
  landing history, backlog, and release-contour document
- root `docs/` now uses role-named districts instead of a flat surface list,
  preserving the AbyssOS source/runtime split in the folder topology itself
- the Intel workstation route now has explicit service-selection docs, a Gemma
  4 E2B `llama.cpp` Vulkan lane, an opt-in Qwen3 rerank API profile, thin-host
  guard overlays, a protected TTS keep-warm timer, and the first source-linked
  RAG orchestration profile
- the observability route now adds internal-only Loki and Grafana Alloy so
  PromQL, LogQL, dashboards, and alerting live in the same explicit profile
- MCP access-plane and agent-skill projection surfaces now include the current
  decision-lane and session-memory operator routes needed by this release line

### Added

- `docs/decisions/AGENTS.md`, `docs/decisions/TEMPLATE.md`,
  `scripts/decision_indexes.py`, `scripts/generate_decision_indexes.py`,
  `scripts/validate_decision_records.py`, and `tests/test_decision_records.py`
  as the local canonical decision-record contract and validation lane
- `docs/decisions/ABYSS-STACK-D-0017-direction-history-decision-surface-roles.md` as
  the rationale for the `ROADMAP.md`, `CHANGELOG.md`, and `docs/decisions/`
  role split
- `docs/routes/START_HERE_ROUTE_CONTRACT.md` as the source-checkout route-mode
  contract for root entry surfaces
- `docs/{routes,runtime,install,operations,profiles,governance,legacy}/README.md`
  as short district maps for repo-wide documentation
- `docs/RELEASING.md` as a compatibility route for release tooling and older
  links, pointing to the authoritative `docs/governance/RELEASING.md` flow
- `docs/decisions/ABYSS-STACK-D-0020-docs-district-topology.md` as the rationale for
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
  `docs/decisions/ABYSS-STACK-D-0032-mcp-services-topology.md` as the canonical MCP
  service-package topology for `aoa-memo-mcp`
- `mcp/services/abyss-machine-mcp/` and
  `docs/decisions/ABYSS-STACK-D-0036-abyss-machine-mcp-access-plane.md` as the
  stack-owned, read-only MCP access plane over `abyss-machine` host read models
- `memo/` reviewed-intake packet for the post-2026-05-22 MCP access-plane
  expansion, preserving that `abyss-stack` owns service packaging while
  `aoa-evals`, `abyss-machine`, and `aoa-memo` keep their respective authority
- `docs/runtime/SERVICE_SELECTION.md` as the source-level service-selection
  guide for lean Intel, full Intel, optional workflows, tools, observability,
  reranking, and protected speech routes
- `loki` and `alloy` in `compose/modules/60-monitoring.yml`, with public-safe
  Loki, Alloy, Grafana datasource, Prometheus scrape, alert, layout, probe,
  service-selection, and decision-record coverage for LogQL observability
- `.agents/skills/aoa-decision*` and `.agents/skills/aoa-memo-writeback` as
  repo-local projection routes into the sibling `aoa-skills` canon for
  decision lookup, decision correction/creation, and memory writeback work
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
- `docs/decisions/ABYSS-STACK-D-0028-intel-inference-and-rerank-service-selection.md`
  as the rationale for the current Gemma, OVMS embeddings, Qwen3 reranking,
  protected TTS, and optional-service split
- `docs/decisions/ABYSS-STACK-D-0038-canonical-decision-ids-and-indexes.md`
  and generated `docs/decisions/indexes/` read models for stable
  `ABYSS-STACK-D-####` decision lookup
- `docs/validation/` and `docs/testing/` as the source-owned districts for
  validation command authority, validator topology, script topology, test
  topology, lane manifests, and machine-readable inventories
- `scripts/validation_lanes.py`, `scripts/ci_gate.py`, and topology tests for
  manifest-backed validation lanes, script surfaces, validator surfaces, and
  test inventory coverage
- `scripts/validators/script_surface.py` as the first focused owner module
  extracted from `scripts/validate_stack.py`
- `scripts/validators/source_hygiene.py` as the focused source/runtime hygiene
  module extracted from `scripts/validate_stack.py`
- `scripts/validators/source_structure.py` as the focused required-file and
  root residual topology module extracted from `scripts/validate_stack.py`
- `scripts/validators/service_selection.py` and focused tests for the runtime
  service-selection policy and screenshot inventory validator split
- `scripts/validators/sync_parity.py` and focused tests for sync-managed
  source enumeration and source/deployed Configs parity
- `scripts/validators/questbook_surface.py` and focused tests for quest schema
  envelopes, quest source topology, generated quest examples, and RPG runtime
  read-model guards
- `scripts/validators/federation_surface.py` and focused tests for federation
  runtime-loaded config input coverage, upstream bridge template posture, and
  active-vs-legacy bridge language, and federation landing docs
- `scripts/validators/federation_runtime_seams.py` and focused tests for
  memo/eval/playbook/KAG runtime seam docs, bounded export examples, and A2A
  handoff posture
- `scripts/validators/diagnostic_spine.py` and focused tests for diagnostic
  surface docs, schemas, examples, generated catalog refs, overlay skill
  posture, and repair handoff readiness
- `scripts/validators/runtime_hygiene.py` and focused tests for runtime
  gateway cache/usage status-readout docs, schemas, examples, and
  readiness-only doctor split posture
- `scripts/validators/machine_fit.py` and focused tests for reference-platform,
  host-facts, machine bridge, machine-fit record, freshness gate, and
  platform-adaptation posture
- `scripts/validators/return_policy.py` and focused tests for return-policy
  config routes, render-truth autonomy route refs, and runtime return schema
  identity
- `scripts/validators/branch_policy.py` and focused tests for CONTRIBUTING
  branch-policy routing, canonical `main` posture, branch retirement language,
  and source/runtime checkout distinction
- `scripts/validators/root_routes.py` and focused tests for root design cards,
  start-here route exposure, front-door route modes, and command-authority
  handoff language
- `scripts/validators/decision_surface.py` and focused tests for decision
  route cards, template shape, validator/generator handoffs, and
  `test_decision_records.py` route exposure
- `scripts/validators/mechanics_topology.py` and focused tests for mechanics
  atlas routes, package card headings, part required files, active part names,
  archive routes, and marker-only artifact posture
- `scripts/validators/profile_topology.py` and focused tests for
  composition-first profiles and presets, compose module dependency guards,
  profile workflow rehearsal, sidecar/n8n/warmup posture, and active profile
  route language
- `scripts/validators/runtime_route_contracts.py` and focused tests for stale
  deployed-root bans, root README route focus, runtime/federation route docs,
  and governed policy/catalog envelope checks
- `scripts/validators/inference_pilot_compatibility.py` and focused tests for
  active local-trials bridge posture, preserved gate IDs, legacy W0-W4 metadata
  containment, and active LangGraph/llama.cpp compatibility language
- `scripts/validators/active_topology_language.py` and focused tests for
  retired phase/wave/seed wording, RPG runtime projection language, playbook
  activation allowlist drift, and route-api bridge language
- `scripts/validators/agent_skill_projection.py` and focused tests for
  repo-local `.agents/skills` projection, sibling `aoa-skills` targets,
  checkout-safe target files, local overlays, and diagnostic overlay installs

### Changed

- `scripts/validate_stack.py` is now a root validation orchestrator instead of
  a public compatibility-wrapper API; focused tests call validator modules
  directly and legacy root-named test routes were replaced with
  owner-shaped test names.
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
- `release_check.py` now reads the release command sequence from
  `docs/validation/validation_lanes.json`, and GitHub `Repo Validation` routes
  reusable release and shellcheck commands through `scripts/ci_gate.py`
- `aoa-session-memory-mcp` now reports a live SQLite graph store separately
  from a missing exported sidecar, keeps bounded graph maintenance in the MCP
  plan, and leaves full sidecar export under explicit offline operator commands
- `validate_stack.py` now delegates script/operator-wrapper validation to the
  focused `scripts/validators/script_surface.py` module while keeping root API
  compatibility for existing tests and callers
- `validate_stack.py` now delegates public mirror hygiene, host-local checkout
  path bans, moved mechanic doc refs, and stale active sibling root checks to
  `scripts/validators/source_hygiene.py`
- `validate_stack.py` now delegates required source-file checks, managed unit
  skeleton checks, and residual root/doc district topology guards to
  `scripts/validators/source_structure.py`
- `validate_stack.py` now delegates service-selection policy and screenshot
  inventory checks to `scripts/validators/service_selection.py`
- `validate_stack.py` now delegates sync-managed item coverage, runtime
  Configs mirror checks, and source/deployed parity to
  `scripts/validators/sync_parity.py`
- `validate_stack.py` now delegates questbook, quest source, generated quest
  example, and RPG runtime read-model checks to
  `scripts/validators/questbook_surface.py`
- `validate_stack.py` now delegates federation required runtime input coverage
  upstream compatibility bridge template/language checks, and federation
  landing-doc guards to
  `scripts/validators/federation_surface.py`
- `validate_stack.py` now delegates memo/eval/playbook/KAG runtime seam export
  and advisory-route guards to `scripts/validators/federation_runtime_seams.py`
- `validate_stack.py` now delegates diagnostic-spine surface contracts to
  `scripts/validators/diagnostic_spine.py`, while the generated diagnostic
  catalog lists the focused module and test in its validation refs
- `validate_stack.py` now delegates runtime gateway cache and usage
  status-readout contracts to `scripts/validators/runtime_hygiene.py`
- `validate_stack.py` now delegates machine-fit evidence posture checks to
  `scripts/validators/machine_fit.py`
- `validate_stack.py` now delegates return-policy runtime contract checks to
  `scripts/validators/return_policy.py`
- `validate_stack.py` now delegates branch-governance policy checks to
  `scripts/validators/branch_policy.py`
- `validate_stack.py` now delegates root design and entry-route checks to
  `scripts/validators/root_routes.py`
- `validate_stack.py` now delegates decision-surface route checks to
  `scripts/validators/decision_surface.py`
- `validate_stack.py` now delegates mechanics topology checks to
  `scripts/validators/mechanics_topology.py`
- `validate_stack.py` now delegates runtime profile topology checks to
  `scripts/validators/profile_topology.py`
- `validate_stack.py` now delegates runtime route contract checks to
  `scripts/validators/runtime_route_contracts.py`
- `validate_stack.py` now delegates inference-pilot compatibility checks to
  `scripts/validators/inference_pilot_compatibility.py`
- `validate_stack.py` now delegates active-topology language checks to
  `scripts/validators/active_topology_language.py`
- `validate_stack.py` now delegates agent skill projection checks to
  `scripts/validators/agent_skill_projection.py`
- `compose/AGENTS.md` now routes module dependency contract changes to
  `scripts/validators/profile_topology.py`
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
- all existing decision records now use full canonical `ABYSS-STACK-D-####`
  filenames, in-file decision IDs, `Index Metadata`, and generated lookup
  indexes, with `scripts/release_check.py` running the decision validator before
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

### Included in this release

Cross-check source: first-parent history, merged PRs, release-note follow-ups,
and the repository diff from `v0.2.2` through the published `v0.4.0` tag.

- root and route surfaces: nested `AGENTS.md` guardrails, slim root `AGENTS`,
  source-only mirror posture, GitHub surface separation, branch policy,
  release/governance docs, route-mode README, design surfaces, roadmap routing,
  docs district topology, and source/runtime path boundaries
- mechanics topology: package-card spines, part-local operator backends,
  package-local legacy containment, active-vs-archive language, quiet bridge
  routes, and package docs for config projection, runtime lifecycle, machine
  fit, inference pilots, federation seams, governed execution, diagnostic
  spine, runtime repair, Agon runtime, and experience runtime
- runtime profiles and services: `substrate`, `local-worker`, `intel-worker`,
  `fallback-gateway`, `workflows`, `tools`, `reranking`, `rag`,
  `speech-fast-experimental`, Gemma 4 E2B `llama.cpp` tuning, Qwen3 reranking,
  RAG orchestration, BabelVox/OpenVINO TTS, resource-guard overlays, and
  internal-only Loki/Alloy observability
- systemd and host-operation surfaces: source-managed user and system unit
  skeletons, service install routes, smoke/internal probes, warmup/status/log
  wrappers, resource-guard application, host-facts, machine-fit, platform
  adaptation, Windows/WSL bridge scripts, protected TTS warmth, and
  `abyss-machine` read-only bridge integration
- MCP access planes: `aoa-memo-mcp`, `aoa-evals-mcp`, `abyss-machine-mcp`,
  `aoa-session-memory-mcp`, and `aoa-decisions-mcp`, including memo port
  intake, corpus-backed memo search, memory writeback packet routing,
  workspace-map port discovery, runtime export filtering, SQLite graph-store
  sidecar posture, and read-only decision graph impact packets
- decision and graph surfaces: canonical `ABYSS-STACK-D-####` records, generated
  decision indexes, generated decision graph, workspace decision graph schemas,
  graph builder/validator scripts, modeled decision-surface list contracts,
  route-anchor impact packets, and decision-surface coverage guards
- federation and runtime seams: effective runtime input alignment,
  route-api/federation bridge compatibility IDs, eval/playbook/memo/KAG seam
  contracts, synchronized bridge eval templates, sibling mirror topology for
  aoa-agents, aoa-memo, and aoa-playbooks, and active legacy-archive
  dependency removal
- quests, memo, and recurrence read models: quest lane/state topology, quest
  examples and schemas, memo intake/receipts/candidates, reviewed forwarding
  receipts, recurrence manifests, diagnostic catalogs, degradation receipts,
  repair-safe closeout, A2A return dry-run, and memo contradiction sidecar
  validation
- validation and CI: `ci_gate.py`, release-check synthetic Configs parity,
  command-authority manifests, script/test/validator inventories, focused
  validator modules, nested AGENTS validation, schema contracts, compose/RAG
  contract tests, service-selection tests, decision-record tests, workspace
  decision-graph tests, Windows host bridge CI, and GitHub Repo Validation

### Validation

The release was verified through the then-current source, topology, generated,
test, and release lanes. Exact commands remain in the active validation owner
surfaces rather than this historical log.
- GitHub `Repo Validation` and `validate-windows-host-bridge` on the release
  landing PRs

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

The release was verified through the then-current release route.

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

The release was verified through the then-current release route.

### Notes

- this patch extends bounded runtime recovery and advisory posture without
  claiming live deployment mutation from the source repository alone

## [0.2.0] - 2026-04-10

### Summary

- this release adds diagnostic-spine contracts, source-rooted mirror canaries, federated advisory seams, winner-promotion loops, and new OVMS/chat/ToS-graph runtime lanes
- llama.cpp fallback and tuning posture are hardened while runtime docs and AGENTS guidance are aligned around parity, support boundaries, and bounded advisory ownership
- `abyss-stack` remains source-authored on the runtime layer, with deployed state becoming live only after sync into the `Configs` mirror

### Validation

The release was verified through the then-current release route.

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

The baseline was verified through the then-current source, parity, and Python
compilation routes.

### Notes

- this release establishes the source-authored baseline for the runtime layer; deployed runtime state still becomes live only after sync into `/srv/AbyssOS/abyss-stack/Configs`
