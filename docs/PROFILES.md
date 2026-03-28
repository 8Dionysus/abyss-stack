# PROFILES

Profiles are ordered lists of compose modules.

They answer a simple question:

**which parts of the body should be awake right now?**

## Current profiles

### `core`

The smallest useful local substrate:
- `10-storage.yml`
- `20-orchestration.yml`
- `30-local-inference.yml`

### `agentic`

A local agent-facing runtime surface with an Ollama-first embeddings path:
- `10-storage.yml`
- `20-orchestration.yml`
- `30-local-inference.yml`
- `40-llm-gateway.yml`
- `41-agent-api.yml`

### `intel`

The agentic surface plus Intel-oriented inference and an OVMS overlay for the agent API:
- `10-storage.yml`
- `20-orchestration.yml`
- `30-local-inference.yml`
- `31-intel-inference.yml`
- `40-llm-gateway.yml`
- `41-agent-api.yml`
- `42-agent-api-intel.yml`

### `federation`

An opt-in metadata-only federation seam:
- `43-federation-router.yml`

This profile is intended to layer over `agentic` or `intel`, but it may also be run by itself for seam debugging.
It reads a mirrored `aoa-agents` contract seam, an `aoa-routing advisory seam`, an `aoa-memo` recall seam, an `aoa-evals` eval selection seam, an `aoa-playbooks` activation/composition advisory seam, an `aoa-kag` retrieval/regrounding seam, and a source-owned `tos-source` handoff seam through the single localhost-only `route-api`.
It also enables filesystem-first memo export candidates under `${AOA_STACK_ROOT}/Logs/memo-exports/` and filesystem-first eval export candidates under `${AOA_STACK_ROOT}/Logs/eval-exports/`.

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
aoa-profile-modules --profile agentic --profile tools --paths
aoa-profile-endpoints --profile agentic --profile tools
```

## Examples

Bring up the smallest substrate:

```bash
aoa-up --profile core
```

Bring up the main agent runtime:

```bash
aoa-profile-modules --profile agentic --paths
aoa-profile-endpoints --profile agentic
aoa-up --profile agentic
```

Bring up the Intel-aware agent runtime:

```bash
aoa-profile-modules --profile intel --paths
aoa-profile-endpoints --profile intel
aoa-up --profile intel
```

Bring up an agent runtime plus the optional federation seam:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-agents
scripts/aoa-sync-federation-surfaces --layer aoa-routing
scripts/aoa-sync-federation-surfaces --layer aoa-memo
scripts/aoa-sync-federation-surfaces --layer aoa-evals
scripts/aoa-sync-federation-surfaces --layer aoa-playbooks
scripts/aoa-sync-federation-surfaces --layer aoa-kag
scripts/aoa-sync-federation-surfaces --layer tos-source
aoa-profile-modules --profile agentic --profile federation --paths
aoa-profile-endpoints --profile agentic --profile federation
aoa-up --profile agentic --profile federation
```

Bring up an agent runtime plus tools and observability:

```bash
aoa-profile-modules --profile agentic --profile tools --profile observability --paths
aoa-profile-endpoints --profile agentic --profile tools --profile observability
aoa-up --profile agentic --profile tools --profile observability
```

Bring up only observability:

```bash
aoa-up --profile observability
```
