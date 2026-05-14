# MIGRATION FROM `abyss-stack_old`

## Migration thesis

The old repository mixed operational substrate with too much adjacent meaning and too many services in one wide runtime surface.

The new repository keeps the useful body and removes monolith relapse.

## What is retained from the old stack

- rootless Podman and systemd user posture
- the `/abyss` heavy-data assumption as an optional mount
- localhost-first security stance
- operational docs as a core habit
- storage, orchestration, inference, gateway, speech, browser, and monitoring service families

## Canonical root shift

The old stack revolved around `/srv/abyss`.
The new stack now uses `/srv/AbyssOS/abyss-stack` as the canonical deployed runtime root.

## What has already been migrated

### Service modules

- `compose/modules/10-storage.yml`
- `compose/modules/20-orchestration.yml`
- `compose/modules/30-local-inference.yml`
- `compose/modules/31-intel-inference.yml`
- `compose/modules/40-llm-gateway.yml`
- `compose/modules/41-agent-api.yml`
- `compose/modules/50-speech.yml`
- `compose/modules/51-browser-tools.yml`
- `compose/modules/60-monitoring.yml`

### Operational carryover

- rootless and localhost-first posture
- Intel-aware inference branch
- `/srv/AbyssOS/abyss-stack` as the new absolute runtime layout root
- optional heavy-data mount assumptions

## What changes

### Old
- one broad `compose.stack.yml`
- optional layers existed but the stack still felt center-heavy
- infra repo still carried traces of broader cosmology
- canonical runtime root was `/srv/abyss`

### New
- explicit module files by concern
- profile-driven activation
- infra-only ownership boundaries
- sibling AoA repositories stay authoritative for authored meaning
- canonical runtime root is `/srv/AbyssOS/abyss-stack`

## Mapping sketch

- old `README.md` -> new `README.md` plus focused docs
- old `ARCHITECTURE.md` -> `docs/runtime/ARCHITECTURE.md`
- old `REQUIREMENTS.md` -> `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md`
- old `BUILD.md` -> `docs/operations/LIFECYCLE.md`
- old `SECURITY.md` -> `docs/operations/SECURITY.md`
- old compose surfaces -> `compose/modules/*`

## Migration rule

Do not port old files mechanically.
Each old part must answer:
- is it still needed?
- which module owns it?
- is it runtime or authored meaning?
- does it belong in this repository at all?
