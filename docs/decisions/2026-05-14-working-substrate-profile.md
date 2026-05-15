# Working Substrate Profile

Status: accepted
Date: 2026-05-14

## Context

`abyss-stack` should become the place where the real working AbyssOS substrate
is selected and run. Before this decision, the default `core` profile mixed the
service substrate with `llama.cpp` inference. That made the base runtime look
like a local-worker bundle and blurred which services are required for the OS
substrate itself.

The live machine may still choose richer host-local drop-ins such as
`intel-full` plus `federation`; this decision is about the source-owned default
and portable checkout contract, not a live service mutation.

## Options considered

1. Keep `core` as the default source profile and document that it means
   substrate plus inference.
2. Rename `core` directly and force every caller to move at once.
3. Add a conservative `substrate` profile, keep `core` as compatibility, and
   add an explicit `local-worker` layer for the canonical
   `llama.cpp`/`langchain-api` path.

## Decision

`substrate` is the default source-owned runtime profile. It contains the
storage base. `local-worker` contains the canonical `llama.cpp` plus
`langchain-api` worker layer. `core` remains a compatibility bundle for storage
and `llama.cpp` basics, but it no longer carries the default substrate role.

The later same-day
[Workflow Automation Optional Profile](2026-05-14-workflow-automation-optional-profile.md)
decision moved n8n workflow automation out of `substrate` and into the explicit
`workflows` profile.

## Rationale

This keeps the working AbyssOS substrate runnable from `abyss-stack` without
silently pulling workflow automation, model-serving, federation, tools, or
observability into the base. It also avoids a brittle rename that would break
existing habits before the runtime and docs have had time to converge.

The split matches the repository boundary: `abyss-stack` owns runtime selection
and lifecycle, while `abyss-machine` remains the stronger owner of machine
control-plane truth and host facts.

## Consequences

- Default wrapper and source unit behavior are more conservative.
- Operators can still use `core`, `agentic`, `intel`, and existing presets.
- Operators add `workflows` explicitly when n8n is part of the selected run.
- Documentation and CI must rehearse `substrate` and `local-worker` directly so
  the new split does not decay back into implicit `core` law.
- Live runtime drop-ins remain host-local and are not overwritten by this source
  decision.

## Source surfaces

- `compose/profiles/substrate.txt`
- `compose/profiles/workflows.txt`
- `compose/profiles/local-worker.txt`
- `scripts/aoa-lib.sh`
- `systemd/user/podman-compose-abyss.service`
- `docs/profiles/PROFILES.md`
- `docs/profiles/PROFILE_RECIPES.md`
- `docs/runtime/ARCHITECTURE.md`
- `docs/runtime/SERVICE_CATALOG.md`
- `.github/workflows/validate-stack.yml`

## Follow-up route

Revisit through `docs/profiles/PROFILES.md`, `mechanics/runtime-lifecycle/`,
and a new decision record if the working substrate grows beyond storage or if a
future migration retires `core` compatibility.
