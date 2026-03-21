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

A local agent-facing runtime surface:
- `10-storage.yml`
- `20-orchestration.yml`
- `30-local-inference.yml`
- `40-llm-gateway.yml`
- `41-agent-api.yml`

### `intel`

The agentic surface with Intel-oriented inference:
- `10-storage.yml`
- `20-orchestration.yml`
- `30-local-inference.yml`
- `31-intel-inference.yml`
- `40-llm-gateway.yml`
- `41-agent-api.yml`

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

## Examples

Bring up the smallest substrate:

```bash
aoa-up --profile core
```

Bring up the main agent runtime:

```bash
aoa-up --profile agentic
```

Bring up only observability:

```bash
aoa-up --profile observability
```
