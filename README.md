# abyss-stack

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem.

It is **Fedora-first** in deployment posture, while remaining **Windows-usable** for source work, path mapping, and hybrid workflows.

It owns runtime, deployment, storage layout, lifecycle, security, reference platform posture, and infra glue.
It does **not** own the authored meaning of the specialized AoA layers.

## What this repository is for

This repository is the right home for:
- local and hybrid runtime topology
- rootless Podman and systemd user orchestration
- storage and mount contracts
- service modules and deployment profiles
- versioned build contexts for lightweight runtime helper services
- runtime-facing return and bounded context-rebuild policy for agent-facing routes
- security, runbook, backup, and restore posture
- normative host posture and machine-readable host-facts contracts
- platform-adaptation policy and public-safe/private tuning record contracts
- infra helper services that support AoA and ToS

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

## Relationship to the ecosystem

- `Agents-of-Abyss` is the ecosystem center.
- `Tree-of-Sophia` is the knowledge architecture counterpart.
- `aoa-*` repositories own their specialized meaning.
- `abyss-stack` owns the body those layers can run on.

## Start here

1. Read [CHARTER](CHARTER.md).
2. Read [BOUNDARIES](BOUNDARIES.md).
3. Read [docs/ARCHITECTURE](docs/ARCHITECTURE.md).
4. Read [docs/SERVICE_CATALOG](docs/SERVICE_CATALOG.md).
5. Read [docs/PROFILES](docs/PROFILES.md).
6. Read [docs/PRESETS](docs/PRESETS.md).
7. Read [docs/PROFILE_RECIPES](docs/PROFILE_RECIPES.md).
8. Read [docs/RENDER_TRUTH](docs/RENDER_TRUTH.md).
9. Read [docs/RUNTIME_BENCH_POLICY](docs/RUNTIME_BENCH_POLICY.md).
10. Read [docs/INTERNAL_PROBES](docs/INTERNAL_PROBES.md).
11. Read [docs/PATHS](docs/PATHS.md).
12. Read [docs/WINDOWS_BRIDGE](docs/WINDOWS_BRIDGE.md).
13. Read [docs/WINDOWS_SETUP](docs/WINDOWS_SETUP.md).
14. Read [docs/WINDOWS_PERFORMANCE](docs/WINDOWS_PERFORMANCE.md).
15. Read [docs/STORAGE_LAYOUT](docs/STORAGE_LAYOUT.md).
16. Read [docs/REFERENCE_PLATFORM](docs/REFERENCE_PLATFORM.md).
17. Read [docs/REFERENCE_PLATFORM_SPEC](docs/REFERENCE_PLATFORM_SPEC.md).
18. Read [docs/PLATFORM_ADAPTATION_POLICY](docs/PLATFORM_ADAPTATION_POLICY.md).
19. Read [docs/BRANCH_POLICY](docs/BRANCH_POLICY.md).
20. Read [docs/MEMO_RUNTIME_SEAM](docs/MEMO_RUNTIME_SEAM.md).
21. Read [docs/MODEL_PROFILES](docs/MODEL_PROFILES.md).
22. Read [docs/CONTEXT_BUDGET_POLICY](docs/CONTEXT_BUDGET_POLICY.md).
23. Read [docs/RECURRENCE_RUNTIME_POLICY](docs/RECURRENCE_RUNTIME_POLICY.md).
24. Read [docs/DEPLOYMENT](docs/DEPLOYMENT.md).
25. Read [docs/FIRST_RUN](docs/FIRST_RUN.md).
26. Read [docs/DOCTOR](docs/DOCTOR.md).
27. Read [docs/SECRETS_BOOTSTRAP](docs/SECRETS_BOOTSTRAP.md).
28. Read [docs/LIFECYCLE](docs/LIFECYCLE.md).
29. Read [docs/RUNBOOK](docs/RUNBOOK.md).
30. Read [docs/SECURITY](docs/SECURITY.md).
31. Read [docs/MIGRATION_FROM_OLD](docs/MIGRATION_FROM_OLD.md).

For the shortest next route by intent:
- if you need the ecosystem center, layer map, or federation rules, go to [`Agents-of-Abyss`](https://github.com/8Dionysus/Agents-of-Abyss)
- if you need the knowledge world and authored architecture, go to [`Tree-of-Sophia`](https://github.com/8Dionysus/Tree-of-Sophia)
- if you need reusable practice, go to [`aoa-techniques`](https://github.com/8Dionysus/aoa-techniques)
- if you need bounded execution workflows, go to [`aoa-skills`](https://github.com/8Dionysus/aoa-skills)
- if you need portable proof surfaces, go to [`aoa-evals`](https://github.com/8Dionysus/aoa-evals)
- if you need memory-layer meaning or recall contracts, go to [`aoa-memo`](https://github.com/8Dionysus/aoa-memo)
- if you need the Windows host and WSL bridge workflow, read [docs/WINDOWS_BRIDGE](docs/WINDOWS_BRIDGE.md), [docs/WINDOWS_SETUP](docs/WINDOWS_SETUP.md), and [docs/WINDOWS_PERFORMANCE](docs/WINDOWS_PERFORMANCE.md)
- if you need runtime benchmark ownership, storage, and manifest rules, read [docs/RUNTIME_BENCH_POLICY](docs/RUNTIME_BENCH_POLICY.md)
- if you need normative host posture or machine-readable host-facts capture, read [docs/REFERENCE_PLATFORM](docs/REFERENCE_PLATFORM.md) and [docs/REFERENCE_PLATFORM_SPEC](docs/REFERENCE_PLATFORM_SPEC.md)
- if you need a compact record of platform-specific quirks, adaptations, and portability notes, read [docs/PLATFORM_ADAPTATION_POLICY](docs/PLATFORM_ADAPTATION_POLICY.md)
- if you need the repo merge and branch discipline, read [docs/BRANCH_POLICY](docs/BRANCH_POLICY.md)
- if you need the runtime-side memo mirror, recall seam, or export candidates, read [docs/MEMO_RUNTIME_SEAM](docs/MEMO_RUNTIME_SEAM.md)

`abyss-stack` may consume public return anchors and checkpoint handles from sibling AoA repositories, but it only owns runtime rebuild policy and return-event logging.

## Quick route table

| repository | owns | go here when |
|---|---|---|
| `abyss-stack` | runtime, deployment, storage, lifecycle, and infra glue | you need the body the system runs on |
| `Agents-of-Abyss` | ecosystem identity, layer map, federation rules, program-level direction | you need the center and the constitutional view of AoA |
| `Tree-of-Sophia` | living knowledge architecture for philosophy and world thought | you need the knowledge world rather than the runtime body |
| `aoa-techniques` | reusable engineering practice | you need durable techniques rather than infrastructure modules |
| `aoa-skills` | bounded agent-facing execution workflows | you need executable workflows rather than deployment posture |
| `aoa-memo` | memory objects, recall contracts, and memo-side writeback meaning | you need memory-layer authority rather than runtime export plumbing |
| `aoa-evals` | portable proof surfaces for bounded claims | you need evaluation and quality checks rather than runtime services |

## Repository shape

```text
abyss-stack/
├─ README.md
├─ CHARTER.md
├─ BOUNDARIES.md
├─ ROADMAP.md
├─ AGENTS.md
├─ docs/
├─ schemas/
├─ examples/
├─ compose/
├─ config-templates/
├─ scripts/
├─ systemd/
├─ env/
└─ .github/
```

## Module layout

The stack is organized around explicit compose modules rather than one swollen file:

- `10-storage.yml`
- `20-orchestration.yml`
- `30-local-inference.yml`
- `31-intel-inference.yml`
- `40-llm-gateway.yml`
- `41-agent-api.yml`
- `42-agent-api-intel.yml`
- `50-speech.yml`
- `51-browser-tools.yml`
- `60-monitoring.yml`

## Lifecycle surfaces

The repository now includes:
- profile files under `compose/profiles/`
- preset files under `compose/presets/`
- deployment helpers under `scripts/`
- config-template bootstrap helpers under `scripts/`
- source-managed helper-service build contexts under `config-templates/Services/`
- first-run and profile-introspection helpers under `scripts/`
- host-doctor and bootstrap-rehearsal support
- profile endpoint recipes and endpoint introspection helpers
- internal-only probe helpers for hidden services
- render-truth helpers for actual composed runtime output
- runtime benchmark policy, schema, and example artifacts
- reference-platform schema and host-facts capture support
- platform-adaptation schema, example artifacts, and capture support
- preset-aware composition helpers and preset introspection
- Windows host bridge scripts and WSL guidance docs
- optional compose tuning overlays
- human-facing wrappers under `scripts/`
- a systemd user unit skeleton under `systemd/user/`
- a repository validation workflow under `.github/workflows/`

## Current status

The bootstrap skeleton is in place, the first real services have been migrated from `abyss-stack_old`, and the first profile-aware scripts and unit scaffolding now exist.
The current hardening pass adds named presets on top of profile composition so common runtime bundles can be invoked and inspected as first-class operating modes.

## License

Apache-2.0
