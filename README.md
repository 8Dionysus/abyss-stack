# abyss-stack

`abyss-stack` is the infrastructure substrate of the AoA and ToS ecosystem.

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
6. Read [docs/STORAGE_LAYOUT](docs/STORAGE_LAYOUT.md).
7. Read [docs/LIFECYCLE](docs/LIFECYCLE.md).
8. Read [docs/MIGRATION_FROM_OLD](docs/MIGRATION_FROM_OLD.md).

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
├─ scripts/
├─ systemd/
└─ env/
```

## Module layout

The stack is organized around explicit compose modules rather than one swollen file:

- `10-storage.yml`
- `20-orchestration.yml`
- `30-local-inference.yml`
- `31-intel-inference.yml`
- `40-llm-gateway.yml`
- `41-agent-api.yml`
- `50-speech.yml`
- `51-browser-tools.yml`
- `60-monitoring.yml`

## Lifecycle surfaces

The repository now includes:
- profile files under `compose/profiles/`
- human-facing wrappers under `scripts/`
- a systemd user unit skeleton under `systemd/user/`

## Current status

The bootstrap skeleton is in place, the first real services have been migrated from `abyss-stack_old`, and the first profile-aware scripts and unit scaffolding now exist.
The next work is hardening, cleanup, and gradual reduction of environment-specific assumptions.

## License

Apache-2.0
