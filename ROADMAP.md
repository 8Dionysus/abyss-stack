# ROADMAP

This roadmap tracks runtime-wide direction for `abyss-stack`. It is the
direction surface for the runtime, deployment, storage, lifecycle, machine-fit,
diagnostic, repair, and federation-consumption substrate beneath AoA and ToS.

It is not the roadmap of any one mechanic package and not the release history
of the repository.

## Authority

Root `ROADMAP.md` owns:

- current runtime-wide direction
- runtime horizon posture
- source/runtime parity pressure
- live runtime-loop and cutover pressure
- machine-fit and platform-adaptation pressure
- federation-consumption pressure
- diagnostic and repair posture
- GitHub mirror portability direction
- concrete future triggers that belong to the runtime substrate

It does not own mechanic-local roadmaps, checked landing history, release
history, durable quest state, decision rationale, live runtime receipts, private
machine captures, sibling-repository implementation direction, AoA
constitutional direction, or ToS authored meaning.

Use the stronger surface when the change is narrower:

- mechanic-local future pressure: `mechanics/<package>/ROADMAP.md`
- checked mechanic landings: `mechanics/<package>/LANDING_LOG.md`
- mechanic lineage and legacy bridges: `mechanics/<package>/PROVENANCE.md` and
  package-local `legacy/`
- release-visible repository history: `CHANGELOG.md`
- durable obligations and packet state: `QUESTBOOK.md` and `quests/`
- durable rationale: `docs/decisions/`
- operator runbooks: `docs/install/DEPLOYMENT.md`, `docs/install/FIRST_RUN.md`, and
  `docs/operations/RUNBOOK.md`
- live runtime receipts and private machine state: deployed runtime or machine
  owner surfaces, not the GitHub source mirror
- sibling implementation direction: the sibling repository direction surface

## Update Rule

Update this roadmap when a change moves runtime-wide direction, horizon
posture, source/runtime parity pressure, live cutover posture, machine-fit
posture, federation-consumption posture, diagnostic or repair posture, mirror
portability direction, or a concrete future trigger.

Do not update this roadmap for a local mechanic landing, release note, quest
state move, decision record, generated refresh, or compatibility bridge detail
unless it changes one of those runtime-wide directions. Route those changes to
their owning surfaces instead.

Before closeout, ask: did this change move the runtime direction, or did it
only land a local surface?

## Current Runtime Direction

`abyss-stack` is moving from source-topology cleanup into runtime parity and
operator cutover hardening.

The current direction is:

- keep the source checkout portable as a GitHub mirror while deployed runtime
  state remains outside source
- keep mechanics convex, with package-local parts, roadmaps, landing logs,
  provenance, and legacy containment
- keep root operator commands stable while implementation bodies live beside
  their owning mechanic parts
- make `abyss-stack` the source owner of the working runtime substrate:
  `substrate` starts storage only, while workflows, local-worker,
  fallback-gateway, federation, tools, and observability layers remain explicit
  choices
- keep source/runtime parity explicit through synthetic and live Configs checks
- connect to `abyss-machine` through read-only bridge and machine-fit packets,
  not by absorbing machine ownership
- let federation seams become useful runtime inputs only through explicit,
  bounded consumption decisions
- admit `aoa-sdk` Agent OS plans only through an explicit runtime-owned
  compatibility profile, exact snapshot observation, and governed approval
  boundaries
- keep diagnostic spine and antifragility repair posture as evidence and packet
  routes before live mutation or authority promotion
- keep release history in `CHANGELOG.md`; the current `v0.4.0` contour remains
  runtime-substrate hardening, not AoA/ToS meaning and not a claim of live
  service mutation
- keep the current Intel inference route explicit: Gemma 4 E2B is a measured
  `llama.cpp` Vulkan candidate lane, embeddings stay on OVMS, reranking is a
  separate opt-in wrapper profile, and helper tools, workflows, and dashboards
  stay selected service layers rather than implicit resident growth
- promote RAG through a bounded `rag` profile that composes existing Qdrant,
  Neo4j, OVMS embeddings, reranking, route, and local text lanes before adding
  heavier DAG engines or more resident model services

## Horizon: Runtime Topology

- Current posture:
  mechanics packages are convex, and the compose profile taxonomy now separates
  the working `substrate` base from workflows, local-worker, retained fallback
  gateway, federation, tools, and observability layers.
- Next honest move:
  keep service promotion flowing through named modules, profiles, presets,
  mechanic owners, and validation rather than through implicit runtime growth.
- Guardrail:
  root roadmap does not index every package-local future move or landing
  receipt, and `core` compatibility must not retake the role of default
  substrate law.

## Horizon: Source And Runtime Parity

- Current posture:
  source release checks use synthetic Configs parity by default, while live
  parity remains an explicit operator choice.
- Next honest move:
  keep `SOURCE_RUNTIME_PARITY_PACKET.md` and sync validation current as root and
  mechanics surfaces move.
- Guardrail:
  source parity is not live service health, and live runtime state is not
  committed to the GitHub mirror.

## Horizon: MCP Access Fabric

- Current posture:
  the shared owner adapters retain direct, authenticated loopback access while
  the first `abyss-stack-mcp` source candidate separates compact runtime
  observation from immutable non-executing plan preparation. The two stack
  contours have disjoint tools, ports, scopes, client identities, and
  atomically provisioned credentials. Their managed environment binds deployed
  source to an exact artifact-hashed lock and cannot be replaced while either
  plane is active. Neither contour is admitted or live merely because its
  package and unit files exist.
- Next honest move:
  land and deploy the typed source-to-runtime provenance spine, generate one
  secret-free runtime observation from exact source and deployed identities,
  then advance read and candidate processes independently through registry
  shadow, consumer schema observation, grounded canary, central proof, owner
  acceptance, and rollback evidence.
- Guardrail:
  `abyss-stack-mcp` is runtime evidence and bounded plan preparation, not a
  gateway, domain authority, proof owner, or implicit runtime-effect plane.

## Horizon: Live Runtime Cutover

- Current posture:
  live cutover has a packet route, and the first route-api health drift was
  closed as an operator-gated repair.
- Next honest move:
  rerun the live cutover packet before promoting federation seams or
  runtime-loop consumers into live posture.
- Guardrail:
  a green source checkout does not prove deployed service readiness.

## Horizon: Machine Fit

- Current posture:
  machine facts, platform adaptation, Windows bridge, model cards, and fit
  records live under `mechanics/machine-fit/`.
- Next honest move:
  recheck machine-fit packets after host drift, platform drift,
  model-selection drift, or Windows/WSL path changes.
- Guardrail:
  `abyss-machine` remains the stronger owner of machine control-plane truth.

## Horizon: Local Worker And Inference

- Current posture:
  `langchain-api` on `5403` backed by `llama.cpp` is the bounded promoted
  local-worker posture, with LangGraph adopted for bounded long-horizon flows.
  On the Intel reference route, Gemma 4 E2B is an explicit `llama.cpp` Vulkan
  candidate lane, OVMS remains the embeddings seam, and Qwen3 reranking is an
  opt-in `reranking` profile through a dedicated OpenVINO wrapper.
- Next honest move:
  keep old trial IDs behind compatibility bridges while current trial,
  model-card, benchmark, service-selection, and promotion surfaces use
  role-level names. Promote or replace a serving lane only after a measured
  packet proves the new route.
- Guardrail:
  optional model trials are not ordinary first-run bootstrap, and preserved
  runner IDs are not active topology names. Do not treat the current reranker
  wrapper as proof that the same Qwen3 artifact is an OVMS `/v3/rerank`
  drop-in.

## Horizon: Federation Consumption

- Current posture:
  memo, eval, playbook, RPG runtime, and ToS graph seams are bounded and
  opt-in. The KAG seam additionally has a source-owned tiered-family
  materializer that admits machine-verified owner releases into a local CAS,
  keeps partial hydration as candidate state, and preserves the five-operation
  MCP read boundary. Routing has separate canary and receipt-bound canonical
  cutover paths. The source migration removes ordinary checkout-backed routing
  sync, predecessor governed mutation, and executable predecessor trial
  dependencies while retaining the stable ABI and compatibility rollback.
- Next honest move:
  prove shadow publication, five-owner canary externalization, selective
  projection refresh, and a verified 24-owner composition before treating the
  new KAG distribution route as the only live path. For routing, land the
  coordinated SDK-first owner wave, then collect consecutive SDK-canonical
  validation and real execution cycles before compatibility exit. Keep the
  predecessor rollback tree and archival stop-line until those gates close.
- Guardrail:
  federation consumption does not transfer AoA, ToS, skill, memo, eval,
  playbook, routing, KAG, stats, or agent authority into `abyss-stack`.

## Horizon: Agent OS Governed Execution

- Current posture:
  one local subprocess adapter admits three exact owner-pinned contours:
  governed `bounded_change_safe`, reviewed A2A return, and runtime degradation
  pause/restore/resume. Only repository mutation delegates to the governed
  runner and its two explicit approvals.
- Next honest move:
  exercise conflicting and incomplete multi-agent returns plus isolated
  service-failure restoration, while composing eval verdicts and memory
  receipts outside the runtime adapter.
- Guardrail:
  an SDK plan is not runtime permission, runtime evidence is not an eval
  verdict, and runtime completion is not final reviewed closeout.

## Horizon: Diagnostics And Repair

- Current posture:
  diagnostic spine and runtime repair expose read-only diagnostics, companion
  artifacts, degradation receipts, and repair-safe closeout contracts.
- Next honest move:
  use diagnostic drift and repair handoff packets to guide operator choices
  before introducing live mutation.
- Guardrail:
  diagnosis, degradation evidence, and repair-safe closeout are not automatic
  repair authority.

## Horizon: Mirror Portability

- Current posture:
  the GitHub mirror is source/install-only and carries docs, templates, schemas,
  examples, tests, workflows, and scripts, not live state.
- Next honest move:
  keep `.gitignore`, hygiene validation, and release checks focused on obvious
  private/heavy/live tracked artifacts without overfitting local policy.
- Guardrail:
  public examples and placeholders stay allowed; secrets, logs, models,
  rendered private config, databases, and private captures stay out.

## When The Time Comes

Use this block for runtime-wide work that is not useful to land now but has a
clear future trigger.

- Promote a federation seam from advisory to live consumer only after the seam
  has an explicit source-owner boundary, compatibility route, runtime input
  contract, and rollback story.
- Add stronger live runtime readiness checks only when source parity, deployed
  Configs parity, and current `aoa-status --autonomy --json` evidence show a
  stable repeated need.
- Add shared validator helpers only after repetition across several mechanics
  makes extraction simpler than local clarity.
- Add broader machine-readable direction indexes only after another tool
  consumes the direction data directly.

An item belongs here only when its trigger is concrete and runtime-wide. If the
future pressure is mechanic-local, use `mechanics/<package>/ROADMAP.md`. If it
is a durable obligation, use `QUESTBOOK.md` and `quests/`. If it is rationale,
use `docs/decisions/`.

## Standing Direction

Across all horizons:

- protect source/runtime boundaries
- keep runtime mechanics modular
- keep operator commands stable and implementations owner-local
- keep live mutation explicit and reversible
- keep sibling-owner meaning out of runtime infrastructure
- make every new surface easier to route than the one it replaces
