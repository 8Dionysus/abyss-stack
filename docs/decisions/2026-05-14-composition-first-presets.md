# Composition-First Presets

Status: accepted
Date: 2026-05-14

## Context

After `substrate` became the source-owned default runtime base, the named
presets still expanded through broad `agentic` and `intel` profiles. Those
profiles were runnable and useful, but they hid the actual composition:
substrate, worker, accelerator, helper, federation, and observability layers.

That made the profile topology less convex than the source/runtime design
claimed. A preset could look current while still leaning on older all-in-one
profile names.

## Options considered

1. Keep presets expanding through `agentic` and `intel`.
2. Delete or rename `agentic` and `intel` immediately.
3. Make presets expand through `substrate` plus explicit worker layers, add
   `intel-worker`, and keep `agentic` and `intel` runnable as compatibility
   profiles.

## Decision

Named presets now compose the current layers directly:

- agent presets use `substrate + local-worker`
- Intel presets use `substrate + intel-worker`
- helper, federation, and observability profiles remain explicit add-ons

`intel-worker` is the reviewed Intel worker layer containing the canonical
`llama.cpp`/`langchain-api` path plus the OVMS embeddings seam. The older
`agentic` and `intel` profiles remain runnable compatibility entrypoints, but
new presets and active route examples should not depend on them as hidden
bases.

## Rationale

This keeps `abyss-stack` honest as the owner of the working runtime substrate.
The source checkout now shows the actual layer stack in the preset files
instead of burying it inside broad profile names.

Keeping compatibility profiles avoids a brittle operator break while still
moving the active topology toward role-named layers.

## Consequences

- Preset expansion is easier to inspect and test.
- `agent-full` and `intel-full` remain stable command names, but their internal
  composition is clearer.
- `agentic` and `intel` must stay documented as compatibility routes unless a
  later migration retires them.
- Validators and tests should fail if presets drift back to broad hidden bases.

## Source surfaces

- `compose/profiles/intel-worker.txt`
- `compose/presets/`
- `compose/profiles/README.md`
- `docs/profiles/PROFILES.md`
- `docs/profiles/PRESETS.md`
- `docs/profiles/PROFILE_RECIPES.md`
- `scripts/validate_stack.py`
- `tests/test_profile_composition.py`

## Follow-up route

Revisit through `docs/profiles/PROFILES.md`, `compose/profiles/README.md`, and
`mechanics/runtime-lifecycle/` if a later migration retires the compatibility
profiles or turns an accelerator lane into a different promoted worker path.
