# MIGRATION FROM `abyss-stack_old`

## Migration thesis

The old repository mixed operational substrate with too much adjacent meaning and too many services in one wide runtime surface.

The new repository keeps the useful body and removes monolith relapse.

## What is retained from the old stack

- rootless Podman and systemd user posture
- `/srv/abyss` and `/abyss` storage assumptions
- localhost-first security stance
- operational docs as a core habit
- storage, orchestration, inference, gateway, speech, browser, and monitoring service families

## What changes

### Old
- one broad `compose.stack.yml`
- optional layers existed but the stack still felt center-heavy
- infra repo still carried traces of broader cosmology

### New
- explicit module files by concern
- profile-driven activation
- infra-only ownership boundaries
- sibling AoA repositories stay authoritative for authored meaning

## Mapping sketch

- old `README.md` -> new `README.md` plus focused docs
- old `ARCHITECTURE.md` -> `docs/ARCHITECTURE.md`
- old `REQUIREMENTS.md` -> `docs/REFERENCE_PLATFORM.md`
- old `BUILD.md` -> `docs/LIFECYCLE.md`
- old `SECURITY.md` -> `docs/SECURITY.md`
- old giant compose surfaces -> `compose/modules/*`

## Migration rule

Do not port old files mechanically.
Each old part must answer:
- is it still needed?
- which module owns it?
- is it runtime or authored meaning?
- does it belong in this repository at all?
