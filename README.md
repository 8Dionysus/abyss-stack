# abyss-stack

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem.

It is **Fedora-first** in deployment posture, while remaining **Windows-usable** for source work, path mapping, and hybrid workflows.

It owns runtime, deployment, storage layout, lifecycle, security, and infra glue.
It does **not** own the authored meaning of the specialized AoA layers.

## What this repository is for

This repository is the right home for:
- local and hybrid runtime topology
- rootless Podman and systemd user orchestration
- storage and mount contracts
- service modules and deployment profiles
- security, runbook, backup, and restore posture
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
6. Read [docs/PROFILE_RECIPES](docs/PROFILE_RECIPES.md).
7. Read [docs/INTERNAL_PROBES](docs/INTERNAL_PROBES.md).
8. Read [docs/PATHS](docs/PATHS.md).
9. Read [docs/STORAGE_LAYOUT](docs/STORAGE_LAYOUT.md).
10. Read [docs/DEPLOYMENT](docs/DEPLOYMENT.md).
11. Read [docs/FIRST_RUN](docs/FIRST_RUN.md).
12. Read [docs/DOCTOR](docs/DOCTOR.md).
13. Read [docs/SECRETS_BOOTSTRAP](docs/SECRETS_BOOTSTRAP.md).
14. Read [docs/LIFECYCLE](docs/LIFECYCLE.md).
15. Read [docs/MIGRATION_FROM_OLD](docs/MIGRATION_FROM_OLD.md).

For the shortest next route by intent:
- if you need the ecosystem center, layer map, or federation rules, go to [`Agents-of-Abyss`](https://github.com/8Dionysus/Agents-of-Abyss)
- if you need the knowledge world and authored architecture, go to [`Tree-of-Sophia`](https://github.com/8Dionysus/Tree-of-Sophia)
- if you need reusable practice, go to [`aoa-techniques`](https://github.com/8Dionysus/aoa-techniques)
- if you need bounded execution workflows, go to [`aoa-skills`](https://github.com/8Dionysus/aoa-skills)
- if you need portable proof surfaces, go to [`aoa-evals`](https://github.com/8Dionysus/aoa-evals)

## Quick route table

| repository | owns | go here when |
|---|---|---|
| `abyss-stack` | runtime, deployment, storage, lifecycle, and infra glue | you need the body the system runs on |
| `Agents-of-Abyss` | ecosystem identity, layer map, federation rules, program-level direction | you need the center and the constitutional view of AoA |
| `Tree-of-Sophia` | living knowledge architecture for philosophy and world thought | you need the knowledge world rather than the runtime body |
| `aoa-techniques` | reusable engineering practice | you need durable techniques rather than infrastructure modules |
| `aoa-skills` | bounded agent-facing execution workflows | you need executable workflows rather than deployment posture |
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
- deployment helpers under `scripts/`
- config-template bootstrap helpers under `scripts/`
- first-run and profile-introspection helpers under `scripts/`
- host-doctor and bootstrap-rehearsal support
- profile endpoint recipes and endpoint introspection helpers
- internal-only probe helpers for hidden services
- human-facing wrappers under `scripts/`
- a systemd user unit skeleton under `systemd/user/`
- a repository validation workflow under `.github/workflows/`

## Current status

The bootstrap skeleton is in place, the first real services have been migrated from `abyss-stack_old`, and the first profile-aware scripts and unit scaffolding now exist.
The current hardening pass adds internal-only probes so hidden services are no longer treated as a blind spot after startup.

## License

Apache-2.0
