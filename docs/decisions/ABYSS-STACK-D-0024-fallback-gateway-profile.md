# Fallback Gateway Profile

- Decision ID: ABYSS-STACK-D-0024
- Status: accepted
- Date: 2026-05-14
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-05-14
- Surface classes: runtime profile, source/runtime boundary
- Stack lanes: profiles and presets
- Mechanic parents: config-projection
- Guard families: profile composition, runtime topology
- Posture: accepted fallback profile rationale

## Context

After `substrate` became the source-owned default runtime base, the retained
Ollama and LiteLLM modules still existed as active compose modules but had no
role-named operator profile. That made them look like loose leftovers rather
than an intentional fallback/control lane.

The `llama.cpp` sidecar module is different: it is an inference-pilot sidecar,
not a normal profile member.

## Options considered

1. Leave `30-local-inference.yml` and `40-llm-gateway.yml` as extra-compose-only
   modules.
2. Add them back to `substrate` or `local-worker`.
3. Add an explicit `fallback-gateway` profile and keep the sidecar module out
   of normal profiles.

## Decision

`fallback-gateway` is the retained Ollama plus LiteLLM profile. It is an
explicit operator choice and does not belong to `substrate`. The
`44-llamacpp-agent-sidecar.yml` module remains outside normal profiles and is
activated only through the inference-pilot route or explicit extra compose
selection.

Ollama warmup for this retained lane is opt-in. The canonical `llama.cpp`
local-worker path may warm by default when selected, but the fallback gateway
requires `AOA_OLLAMA_WARMUP_ENABLED=true` before `aoa-warmup` keeps an Ollama
model resident.

## Rationale

This keeps fallback capability available without making it part of the working
AbyssOS base. It also prevents the old gateway lane from becoming an orphaned
module family that future agents either forget or accidentally re-promote.

The split preserves the current local-worker path: `llama.cpp` plus
`langchain-api` stays the promoted worker lane, while Ollama plus LiteLLM stays
a retained control and rollback lane.

## Consequences

- `fallback-gateway` can be rendered, inspected, waited on, and smoked like
  other normal profiles.
- `substrate` remains storage only; workflow automation has its own explicit
  `workflows` profile.
- fallback-gateway startup does not silently warm or pin an Ollama model unless
  the operator opts in.
- CI and validation must keep the fallback profile and sidecar stop-line from
  drifting.
- Future retirement of Ollama/LiteLLM should remove or archive this profile
  deliberately rather than leaving orphan modules behind.

## Source surfaces

- `compose/modules/README.md`
- `compose/profiles/README.md`
- `compose/profiles/fallback-gateway.txt`
- `docs/profiles/PROFILES.md`
- `docs/profiles/PROFILE_RECIPES.md`
- `docs/runtime/ARCHITECTURE.md`
- `docs/runtime/SERVICE_CATALOG.md`
- `mechanics/runtime-lifecycle/parts/start-stop/aoa_warmup.sh`
- `mechanics/runtime-lifecycle/parts/start-stop/tests/test_aoa_warmup.py`
- `.github/workflows/validate-stack.yml`
- `scripts/validate_stack.py`

## Follow-up route

Revisit through `mechanics/inference-pilots/`, `mechanics/runtime-lifecycle/`,
and a new decision record if the fallback gateway is promoted, replaced, or
retired.
