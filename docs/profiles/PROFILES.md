# PROFILES

Profiles are ordered lists of compose modules.

They answer a simple question:

**which parts of the body should be awake right now?**

## Current profiles

### `substrate`

The conservative working service base for the AbyssOS runtime:
- `10-storage.yml`
- `20-orchestration.yml`

This is the default source-owned runtime substrate. It brings up persistence,
retrieval stores, and orchestration without silently choosing a local model
worker, accelerator lane, federation seam, tools, or observability bundle.

### `local-worker`

The canonical local worker layer:
- `32-llamacpp-inference.yml`
- `41-agent-api.yml`

This profile keeps `llama.cpp` and `langchain-api` together without also
claiming to own storage or orchestration. Use it with `substrate` when the
machine should run the promoted local text worker path:

```bash
aoa-up --profile substrate --profile local-worker
```

### `fallback-gateway`

Retained local control and gateway fallback path:
- `30-local-inference.yml`
- `40-llm-gateway.yml`

This profile keeps Ollama and LiteLLM explicit without returning them to the
default substrate. Use it when a rollback/control lane or old gateway-oriented
operator path is intentionally being checked.

### `core`

Compatibility bundle for substrate plus local model-serving basics:
- `10-storage.yml`
- `20-orchestration.yml`
- `32-llamacpp-inference.yml`

Use `substrate` for the default OS runtime base and `substrate + local-worker`
when you also want the agent API. `core` remains useful for older operator
habits and quick storage/orchestration/`llama.cpp` checks.

### `agentic`

A local agent-facing runtime surface with substrate plus the canonical
`llama.cpp` chat path:
- `10-storage.yml`
- `20-orchestration.yml`
- `32-llamacpp-inference.yml`
- `41-agent-api.yml`

This profile keeps the default `POST /run` path on the canonical `langchain-api -> llama.cpp` lane.
Its new `POST /run/federated` path stays opt-in and only becomes useful when the `federation` profile is also present and `AOA_FEDERATED_RUN_ENABLED=true`.

### `intel`

The agentic surface plus the current reviewed Intel-oriented serving seam through OVMS:
- `10-storage.yml`
- `20-orchestration.yml`
- `32-llamacpp-inference.yml`
- `31-intel-inference.yml`
- `41-agent-api.yml`
- `42-agent-api-intel.yml`

In the current promoted posture, this routes embeddings to OVMS while keeping the canonical chat path on `llama.cpp`.
That does not freeze the broader Intel-serving family to embeddings-only forever; wider OVMS, OpenVINO, or OpenVINO GenAI model lanes stay additive and separately reviewed.
The canonical `langchain-api` path now keeps its text target behind a generic runtime-chat seam, so additive Intel text lanes can be configured explicitly without changing what this profile promotes by default.

### `federation`

An opt-in metadata-only federation seam:
- `43-federation-router.yml`

This profile is intended to layer over `agentic` or `intel`, but it may also be run by itself for seam debugging.
It reads a mirrored `aoa-agents` contract seam, an `aoa-routing advisory seam`, an `aoa-memo` recall seam, an `aoa-evals` eval selection seam, an `aoa-playbooks` activation/composition advisory seam, an `aoa-kag` retrieval/regrounding seam, and a source-owned `tos-source` handoff seam through the single localhost-only `route-api`.
It also enables filesystem-first memo export candidates under `${AOA_STACK_ROOT}/Logs/memo-exports/` and filesystem-first eval export candidates under `${AOA_STACK_ROOT}/Logs/eval-exports/`.
`route-api` remains advisory-only in this shape, but when this profile is layered onto `agentic`, `langchain-api` may consume it through `POST /run/federated`.

### `curation`

A route-first ToS graph helper surface:
- `10-storage.yml`
- `52-tos-graph.yml`

This profile keeps the route helper on top of the storage substrate so `neo4j`
is available without silently widening the rest of the runtime.
The current slice stays read-first: it loads canonical ToS files from
`AOA_TOS_ROOT`, exposes a localhost-only helper on `5410`, syncs route-scoped
projection state into Neo4j, and keeps writeback deferred. Machine-fit overlays
that do not touch these services are skipped automatically, so `curation` stays
narrow even when the host has a broader runtime recommendation on file.

### `tools`

Optional helper surfaces:
- `50-speech.yml`
- `51-browser-tools.yml`

### `observability`

Optional monitoring stack:
- `60-monitoring.yml`

## Design rule

Profiles stay small and legible.
A new service should usually enter through a module.
Only then should it be included in one or more profiles.

The optional `llama.cpp` sidecar benchmark lane deliberately stays outside the
default profile and named presets. Use
[LLAMACPP_PILOT](../../mechanics/inference-pilots/parts/llamacpp-pilot/docs/LLAMACPP_PILOT.md)
only when you want an explicit alternate benchmark or promotion surface beyond
the canonical runtime path.

Retained fallback modules should also stay explicit. `30-local-inference.yml`
and `40-llm-gateway.yml` belong to `fallback-gateway`, not to `substrate`.

## Dependency note

Some modules rely on sibling modules being present in the same profile.
The repository validator now checks these inter-module requirements so broken profiles fail fast in CI.

## Composing profiles

Profiles can be combined.
This is the intended way to layer optional surfaces like `tools` and `observability` onto a base runtime path.

### Repeated `--profile`

```bash
aoa-up --profile agentic --profile tools --profile observability
```

### Comma-separated form

```bash
aoa-up --profile agentic,tools,observability
```

## Composition rule

- profiles are resolved in the order you declare them
- modules are appended in that order
- duplicate modules are kept only once, at first appearance
- optional layers should usually come after the base profile

## Practical note

If you want to see the concrete host-facing endpoints and post-start checks for a profile or profile-combination, read:
- [PROFILE_RECIPES](PROFILE_RECIPES.md)

If you want named bundles on top of composition, read:
- [PRESETS](PRESETS.md)

Or use:

```bash
aoa-profile-modules --profile substrate --profile local-worker --paths
aoa-profile-endpoints --profile substrate --profile local-worker
aoa-profile-modules --profile fallback-gateway --paths
```

## Operating routes

Keep this file focused on profile contracts. Use [PROFILE_RECIPES](PROFILE_RECIPES.md)
for startup checks, combined operating examples, federation checks, and
host-facing endpoint expectations.
