# abyss-stack Runtime Mechanics Atlas

This is the branch point for source-owned runtime mechanics in `abyss-stack`.

Use it after the first reading route:

1. `README.md`
2. `CHARTER.md`
3. `BOUNDARIES.md`
4. `docs/ARCHITECTURE.md`
5. `docs/SERVICE_CATALOG.md`
6. `docs/PATHS.md`

When a human or agent asks what kind of runtime move is being made, this atlas
points to the right package, source surfaces, stop-lines, and validation lane.

This file does not create new runtime authority. It keeps the flat docs surface
from doing all routing work at once.

## Root Mechanics Files

The root of `mechanics/` is a dispatcher.

| File | Owns | Must not become |
|---|---|---|
| [AGENTS.md](AGENTS.md) | mechanics-tree editing law, package law, and closeout posture | package doctrine |
| [README.md](README.md) | this atlas, route contract, and package compass | a duplicate of every package card |
| [ARTIFACT_TOPOLOGY.md](ARTIFACT_TOPOLOGY.md) | future placement rules for source docs, scripts, schemas, examples, generated companions, tests, and deployed mirrors | a migration log |

## Movement Contract

The initial mechanics topology created the package homes. Current movement
pushes old flat artifact families into package-local archive homes when the
owning package, validators, tests, generated companions, and route links move
together.

Package cards route to current source surfaces. Moved old files keep
provenance bridges and do not become the active route merely because they are
inside `mechanics/`.

## Package Contract

Every package starts with:

- `AGENTS.md`
- `README.md`
- `DIRECTION.md`
- `PARTS.md`
- `ROADMAP.md`
- `LANDING_LOG.md`
- `docs/README.md`

Each package `README.md` is a runtime mechanic card with these sections:

- `## Mechanic card`
- `### Trigger`
- `### abyss-stack owns`
- `### Stronger owner split`
- `### Inputs`
- `### Outputs`
- `### Must not claim`
- `### Validation`
- `### Next route`

## Compass

| Package | Runtime question | Start here |
|---|---|---|
| [runtime-lifecycle](runtime-lifecycle/README.md) | How is the stack installed, started, stopped, checked, and operated? | `docs/DEPLOYMENT.md`, `docs/FIRST_RUN.md`, `docs/RUNBOOK.md`, `systemd/README.md` |
| [config-projection](config-projection/README.md) | How do source templates become deployed runtime config without smuggling secrets? | `config-templates/`, `env/`, `scripts/aoa-bootstrap-configs`, `scripts/aoa-sync-configs` |
| [machine-fit](machine-fit/README.md) | How does the runtime read host facts, fit, and machine-local tuning without owning the machine? | `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md`, `mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md`, `scripts/aoa-host-facts`, `scripts/aoa-machine-fit` |
| [inference-pilots](inference-pilots/README.md) | How do local model trials, llama.cpp, Qwen, LangGraph, and benchmark promotion stay bounded? | `mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md`, `mechanics/inference-pilots/parts/local-trials/docs/LOCAL_AI_TRIALS.md`, `mechanics/inference-pilots/PROVENANCE.md` |
| [agon-runtime](agon-runtime/README.md) | How do Agon dry-run kernels, event logs, registries, and trials stay local and non-authoritative? | `mechanics/agon-runtime/PROVENANCE.md`, `mechanics/agon-runtime/legacy/INDEX.md` |
| [experience-runtime](experience-runtime/README.md) | How do archived experience runtime contracts, schemas, examples, and tests stay contained? | `mechanics/experience-runtime/PROVENANCE.md`, `mechanics/experience-runtime/legacy/INDEX.md` |
| [federation-seams](federation-seams/README.md) | How does runtime consume sibling owner surfaces without taking their authority? | `mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md`, `mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md`, `mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md`, `scripts/aoa-sync-federation-surfaces` |
| [governed-execution](governed-execution/README.md) | How do local worker runs, autonomy gates, return policy, and candidate exports stay reviewable? | `mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md`, `scripts/aoa-governed-run`, `scripts/aoa-status` |
| [diagnostic-spine](diagnostic-spine/README.md) | How does the runtime locate itself, compare truth goals, and emit repair handoff candidates? | `mechanics/diagnostic-spine/parts/diagnostic-surfaces/docs/DIAGNOSTIC_SPINE.md`, `mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md`, `scripts/aoa-diagnose` |
| [runtime-repair](runtime-repair/README.md) | How do degradation receipts, repair-safe closeout, A2A return, and antifragility stay bounded? | `mechanics/runtime-repair/parts/antifragility-posture/docs/ANTIFRAGILITY_RUNTIME.md`, `mechanics/runtime-repair/parts/repair-safe-closeout/docs/REPAIR_SAFE_CLOSEOUT.md`, `mechanics/runtime-repair/PROVENANCE.md` |

## Package Route Standard

For a package, start with the package `README.md`. Then use:

| Surface | Use for |
|---|---|
| `AGENTS.md` | local law, validation, closeout, and stop-lines |
| `DIRECTION.md` | current operating contour |
| `PARTS.md` | active source-surface map |
| `ROADMAP.md` | next movements and deferred moves |
| `LANDING_LOG.md` | checked landings and validation anchors |
| `docs/` | detailed package-owned notes in later passes |

## Artifact Placement

Mechanics are not only prose. Future package homes may own package-local docs,
schemas, examples, config, generated companions, scripts, and tests when those
artifacts only make sense inside one mechanic.

Use [ARTIFACT_TOPOLOGY.md](ARTIFACT_TOPOLOGY.md) before moving artifacts between
root districts and mechanic homes.

## Validation

For topology and package route checks:

```bash
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```

Package-local future work should add the narrow checks named by that package.
