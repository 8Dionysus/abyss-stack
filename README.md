# abyss-stack

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem.
It is **Fedora-first** in deployment posture and **Windows-usable** for source
work, path mapping, and hybrid workflows.

Use this README as the source checkout front door. It routes readers to the
owner surface that can answer the question. It is not the roadmap, changelog,
decision log, runtime receipt, or package-local inventory.

> Current release: `v0.2.2`. See [CHANGELOG](CHANGELOG.md) for release notes.

## What This Repository Does

| Function | Stronger surface |
|---|---|
| Names the runtime owner lane and what must stay elsewhere | [CHARTER](CHARTER.md), [BOUNDARIES](BOUNDARIES.md) |
| Describes the runtime body this repository should grow toward | [DESIGN](DESIGN.md) |
| Describes the intended shape of agent-facing guidance | [DESIGN.AGENTS](DESIGN.AGENTS.md) |
| Maps concrete runtime topology | [runtime/ARCHITECTURE](docs/runtime/ARCHITECTURE.md), [mechanics](mechanics/README.md) |
| Explains deployment, paths, profiles, presets, and operator flow | [docs](docs/README.md) |
| Holds current runtime-wide direction and future triggers | [ROADMAP](ROADMAP.md) |
| Records release-visible history | [CHANGELOG](CHANGELOG.md) |
| Keeps durable obligations and packet state | [QUESTBOOK](QUESTBOOK.md), [quests](quests/README.md) |
| Explains durable route or topology decisions | [docs/decisions](docs/decisions/README.md) |

This repository is strongest when it keeps the runtime body portable,
recoverable, and explicit. It is weakest when it absorbs sibling meaning or
turns root docs into inventory ledgers.

## Start Here

Read only what matches your entry need.

| Need | Route |
|---|---|
| Shortest honest overview | this README, then [CHARTER](CHARTER.md), [BOUNDARIES](BOUNDARIES.md), [DESIGN](DESIGN.md), and [mechanics](mechanics/README.md) |
| Agent editing route | [AGENTS](AGENTS.md), [DESIGN.AGENTS](DESIGN.AGENTS.md), then the nearest nested `AGENTS.md` |
| Runtime architecture | [runtime/ARCHITECTURE](docs/runtime/ARCHITECTURE.md), [runtime/SERVICE_CATALOG](docs/runtime/SERVICE_CATALOG.md), [profiles/PROFILES](docs/profiles/PROFILES.md), [profiles/PRESETS](docs/profiles/PRESETS.md) |
| Source/install bootstrap | [runtime/PATHS](docs/runtime/PATHS.md), [install/DEPLOYMENT](docs/install/DEPLOYMENT.md), [install/FIRST_RUN](docs/install/FIRST_RUN.md), [mechanics/config-projection](mechanics/config-projection/README.md), [mechanics/runtime-lifecycle](mechanics/runtime-lifecycle/README.md) |
| Runtime operation and incidents | [operations/RUNBOOK](docs/operations/RUNBOOK.md), [scripts/README](scripts/README.md), [mechanics/runtime-lifecycle](mechanics/runtime-lifecycle/README.md) |
| Working substrate selection | [profiles/PROFILES](docs/profiles/PROFILES.md), [profiles/PROFILE_RECIPES](docs/profiles/PROFILE_RECIPES.md), [compose](compose/README.md) |
| Branch and recurrence posture | [governance/BRANCH_POLICY](docs/governance/BRANCH_POLICY.md), [RECURRENCE_RUNTIME_POLICY](mechanics/governed-execution/parts/return-policy/docs/RECURRENCE_RUNTIME_POLICY.md) |
| Host and machine fit | [REFERENCE_PLATFORM](mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md), [REFERENCE_PLATFORM_SPEC](mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md), [MACHINE_FIT_POLICY](mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md), [PLATFORM_ADAPTATION_POLICY](mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md) |
| Windows and WSL bridge | [Windows bridge](mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_BRIDGE.md), [Windows setup](mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_SETUP.md), [Windows performance](mechanics/machine-fit/parts/windows-bridge/docs/WINDOWS_PERFORMANCE.md) |
| Local worker and model trials | [mechanics/inference-pilots](mechanics/inference-pilots/README.md), [LOCAL_AI_TRIALS](mechanics/inference-pilots/parts/local-trials/docs/LOCAL_AI_TRIALS.md), [LLAMACPP_PILOT](mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md), [MODEL_PROFILES](mechanics/machine-fit/parts/inference-tuning/docs/MODEL_PROFILES.md) |
| Runtime federation seams | [mechanics/federation-seams](mechanics/federation-seams/README.md), [MEMO_RUNTIME_SEAM](mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md), [EVAL_RUNTIME_SEAM](mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md), [PLAYBOOK_RUNTIME_SEAM](mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md), [KAG_RUNTIME_SEAM](mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md) |
| Diagnostics and repair posture | [mechanics/diagnostic-spine](mechanics/diagnostic-spine/README.md), [DIAGNOSTIC_SPINE](mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md), [diagnostic surface catalog](mechanics/diagnostic-spine/parts/diagnostic-surfaces/generated/diagnostic_surface_catalog.min.json), [scripts/aoa-diagnose](scripts/aoa-diagnose), [mechanics/runtime-repair](mechanics/runtime-repair/README.md) |

## Route Modes

The route vocabulary behind this entry surface is governed by
[START_HERE_ROUTE_CONTRACT](docs/routes/START_HERE_ROUTE_CONTRACT.md).

| Route mode | Use when | Start surface |
|---|---|---|
| `first-reading` | you need the shortest runtime overview | `README.md` |
| `runtime-design` | the system form, topology, or source/runtime split may move | [DESIGN](DESIGN.md) |
| `agent-guidance` | root or nested agent guidance may move | [DESIGN.AGENTS](DESIGN.AGENTS.md), [AGENTS](AGENTS.md) |
| `source-install` | a checkout must create or refresh a runtime layout | [install/DEPLOYMENT](docs/install/DEPLOYMENT.md), [mechanics/config-projection](mechanics/config-projection/README.md) |
| `runtime-operation` | live operation, logs, status, smoke, or incidents are involved | [operations/RUNBOOK](docs/operations/RUNBOOK.md), [scripts/README](scripts/README.md) |
| `mechanic-change` | a runtime move belongs to a package or part | [mechanics/README](mechanics/README.md) |
| `machine-fit` | host facts, platform adaptation, Windows, or model fit are involved | [mechanics/machine-fit](mechanics/machine-fit/README.md) |
| `diagnostics-repair` | diagnosis, degradation receipts, or repair handoff are involved | [mechanics/diagnostic-spine](mechanics/diagnostic-spine/README.md), [mechanics/runtime-repair](mechanics/runtime-repair/README.md) |
| `direction-change` | runtime-wide direction, horizon, or future trigger changes | [ROADMAP](ROADMAP.md) |
| `release-history` | release-visible history changes | [CHANGELOG](CHANGELOG.md) |
| `decision-rationale` | future agents need to know why a route changed | [docs/decisions](docs/decisions/README.md) |

## Source And Runtime Boundary

- Source checkout: `~/src/abyss-stack` by default, or `${AOA_SOURCE_ROOT}` when
  intentionally relocated.
- Deployed runtime root: `/srv/AbyssOS/abyss-stack`.
- Deployed config tree: `/srv/AbyssOS/abyss-stack/Configs`.
- Source checkout shape is authoritative for the GitHub mirror and install
  source. Do not edit `/srv/AbyssOS/abyss-stack` as if it were the source
  repository.

The GitHub mirror is source/install-only. It may carry docs, templates,
schemas, public examples, tests, workflows, and scripts needed to create a
runtime. It must not carry live `Secrets/`, `Logs/`, `Models/`, `stack.env`,
rendered private config, local databases, model files, or private captures.

Runtime state is created from the checkout through `scripts/aoa-install-layout`,
`scripts/aoa-sync-configs`, and `scripts/aoa-bootstrap-configs`.

## Claim Check

Before trusting or publishing a runtime claim, route it through the smallest
surface that can answer it.

| Claim question | Check |
|---|---|
| Does this belong to the runtime substrate at all? | [CHARTER](CHARTER.md), [BOUNDARIES](BOUNDARIES.md) |
| Does this preserve the intended runtime form? | [DESIGN](DESIGN.md) |
| Does this move runtime-wide direction? | [ROADMAP](ROADMAP.md) |
| Is this release-visible history? | [CHANGELOG](CHANGELOG.md) |
| Is this durable rationale rather than active law? | [docs/decisions](docs/decisions/README.md) |
| Is this mechanic-local doctrine, validation, or landing detail? | [mechanics](mechanics/README.md), then the package `README.md` |
| Is this live state, private machine data, a model, a log, or a secret? | deployed runtime or operator-owned surface, not git |
| Does this copy AoA, ToS, skill, eval, memo, routing, playbook, KAG, stats, or agent authority? | the sibling owner repository |

## Current Contour

The current `v0.2.2` contour is runtime-substrate hardening, not AoA or ToS
meaning and not a claim of live service mutation.

The active source shape is:

- source/install mirror stays portable while live runtime state stays outside
  git
- mechanics are convex packages with parts, local roadmaps, landing logs,
  provenance, validation, and package-local legacy containment
- root operator commands remain stable wrappers while implementation bodies
  live beside their owning mechanic parts
- source/runtime parity uses synthetic release checks by default and live
  checks only through explicit operator intent
- the default source-owned runtime selection is the conservative `substrate`
  profile: storage under `abyss-stack`; workflow automation, local workers,
  retained fallback gateways, federation, tools, and observability layer on top
  explicitly
- `abyss-machine` is consumed through read-only bridge and machine-fit packets
  without transferring machine ownership into this repo
- `langchain-api` on `5403`, `llama.cpp`, and LangGraph remain bounded
  local-worker/inference posture, not proof of full autonomy
- federation seams stay opt-in advisory inputs until explicit live-consumption
  decisions land
- diagnostic spine and runtime repair expose read models, receipts, and
  handoff candidates before any live mutation authority
- MCP access planes live under `MCP/` and expose derived routes, not new source
  authority
- `memo/` is the local runtime memory port for candidates, receipts, exports,
  and stack-local notes

Detailed package contracts belong in mechanic packages. Detailed release
history belongs in `CHANGELOG.md`.

## Mechanics

Runtime moves live under [mechanics](mechanics/README.md). Each package owns
its local card, parts, direction, provenance, roadmap, landing log, and
validation route.

| Package | Use for |
|---|---|
| [runtime-lifecycle](mechanics/runtime-lifecycle/README.md) | layout, start/stop, smoke, logs, status, user units |
| [config-projection](mechanics/config-projection/README.md) | source templates, env examples, bootstrap, sync, rendering |
| [machine-fit](mechanics/machine-fit/README.md) | host facts, fit records, platform adaptation, Windows, model fit |
| [inference-pilots](mechanics/inference-pilots/README.md) | local trials, llama.cpp, Qwen, LangGraph, promotion evidence |
| [federation-seams](mechanics/federation-seams/README.md) | memo, eval, playbook, KAG, RPG, and ToS runtime seams |
| [governed-execution](mechanics/governed-execution/README.md) | governed runs, return policy, autonomy status, candidate exports |
| [diagnostic-spine](mechanics/diagnostic-spine/README.md) | read-only diagnosis, diagnostic artifacts, truth-goal status |
| [runtime-repair](mechanics/runtime-repair/README.md) | degradation receipts, repair-safe closeout, dry-run repair posture |
| [agon-runtime](mechanics/agon-runtime/README.md) | Agon dry-run runtime kernels and contained legacy receipts |
| [experience-runtime](mechanics/experience-runtime/README.md) | contained experience runtime archives and distillation stop-lines |

## Technical Districts

Root-adjacent districts own repository-level function, not mechanic-local
storage.

| District | Use for |
|---|---|
| [compose](compose/README.md) | profile, preset, module, and tuning composition |
| [config-templates](config-templates/README.md) | public-safe config templates synced into runtime |
| [docs](docs/README.md) | repo-level operator, release, path, security, and decision surfaces |
| [env](env/README.md) | public environment examples |
| [MCP](MCP/README.md) | stdio/local access planes for owner-layer context |
| [memo](memo/README.md) | local runtime memory candidates, receipts, exports, and notes |
| [scripts](scripts/README.md) | stable operator wrappers and repository validators |
| [systemd](systemd/README.md) | user-unit source skeletons and managed working-service adapters |
| [tests](tests/README.md) | repository-level tests and validation routes |
| [.agents](.agents/README.md) | repo-local agent overlays and fast-loop lanes |
| [.github](.github/GITHUB_SURFACE.md) | GitHub-native validation and landing surfaces |

District gates explain local handling. They do not replace root authority,
mechanic packages, deployed runtime state, or sibling repositories.

## Validate

Use `scripts/release_check.py` for broad release-facing or repo-wide
validation.

Exact current command lanes live in [AGENTS](AGENTS.md), the nearest nested
`AGENTS.md`, [scripts/README](scripts/README.md), [tests/README](tests/README.md),
and package-local mechanic cards. Diagnostic catalog checks belong to
[diagnostic spine](mechanics/diagnostic-spine/README.md) and the scripts
district, not this front door.

Live runtime checks belong in [operations/RUNBOOK](docs/operations/RUNBOOK.md) and should be run
only when the operator intentionally checks the deployed runtime.

## Working Rule

Grow the stack by making the next runtime route clearer.

Add mechanics, scripts, docs, schemas, examples, tests, decisions, and generated
companions only where they improve reviewability and preserve source/runtime
and sibling-owner boundaries. When a detail belongs to a mechanic, changelog,
roadmap, quest, decision record, deployed runtime, or sibling repository, route
it there instead of loading the README.
