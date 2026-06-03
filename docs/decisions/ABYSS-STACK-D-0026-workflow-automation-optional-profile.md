# Workflow Automation Optional Profile

- Decision ID: ABYSS-STACK-D-0026
- Status: accepted
- Date: 2026-05-14
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-14
- Surface classes: runtime profile, source/runtime boundary
- Stack lanes: profiles and presets
- Mechanic parents: config-projection
- Guard families: profile composition, public-safe config
- Posture: accepted optional workflow rationale

## Context

`20-orchestration.yml` owns n8n and the version-matched external
`n8n-task-runners` sidecar. It was previously selected by `substrate` and by
the broad compatibility profiles. After checking the `abyss-machine` boundary,
n8n is useful as an `abyss-stack` runtime capability but is not required for
the machine control plane or for the working AbyssOS storage substrate.

The operator direction is to keep n8n available in an optional layer, then
decide later whether real workflows should use it.

## Options considered

1. Keep n8n inside `substrate` and let every default runtime bring it up.
2. Remove n8n from the repository until a workflow need is proven.
3. Keep `20-orchestration.yml`, but expose it only through an explicit
   `workflows` profile.

## Decision

n8n workflow automation belongs to the explicit `workflows` profile. The
`substrate` profile is storage-only. Current named presets stay workflows-free.
The broad compatibility profiles no longer hide n8n as part of their module
sets.

`workflows` includes `10-storage.yml` plus `20-orchestration.yml` so it can run
standalone for inspection and still compose cleanly over `substrate` through
normal module de-duplication.

## Rationale

This preserves a real, documented n8n route without claiming that workflow
automation is part of the base OS substrate. It keeps the default runtime small
and avoids teaching future agents that n8n is already a required machine path.
It also avoids deleting a useful module before the project decides whether it
will own live workflow automation through n8n.

## Consequences

- `aoa-up --profile substrate` no longer starts n8n after the source change is
  synced and the runtime is restarted.
- Operators use `--profile workflows` when n8n should be rendered, checked,
  started, waited on, or smoked.
- Existing live services are not mutated by the source decision alone.
- CI and validation must rehearse `workflows` so the optional layer stays
  runnable rather than becoming an archive-shaped leftover.
- A later decision should either promote n8n into a named operating route or
  retire the module deliberately.

## Source surfaces

- `compose/profiles/workflows.txt`
- `compose/profiles/substrate.txt`
- `compose/profiles/core.txt`
- `compose/profiles/agentic.txt`
- `compose/profiles/intel.txt`
- `compose/modules/20-orchestration.yml`
- `docs/profiles/PROFILES.md`
- `docs/profiles/PROFILE_RECIPES.md`
- `docs/runtime/ARCHITECTURE.md`
- `docs/runtime/SERVICE_CATALOG.md`
- `.github/workflows/validate-stack.yml`
- `scripts/validate_stack.py`

## Follow-up route

Revisit through `docs/profiles/PROFILES.md`, `mechanics/runtime-lifecycle/`,
and a new decision record when n8n becomes a live workflow owner, moves into a
named preset, or is retired from the stack.
