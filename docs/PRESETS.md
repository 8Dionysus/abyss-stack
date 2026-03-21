# PRESETS

Presets are named bundles of profiles.

They exist one layer above profile composition:
- modules are the atomic runtime pieces
- profiles are named stacks of modules
- presets are named stacks of profiles

## Why presets exist

Once multi-profile composition became possible, certain combinations turned into common operating modes.
Presets give these combinations stable names, so you do not have to repeat long profile lists for every command.

## Current presets

| preset | resolves to | intended use |
|---|---|---|
| `agent-tools` | `agentic + tools` | local agent runtime with speech and browser tooling |
| `agent-observability` | `agentic + observability` | local agent runtime plus dashboards and metrics |
| `agent-full` | `agentic + tools + observability` | generic local agent runtime with helpers and visibility |
| `intel-tools` | `intel + tools` | Intel-aware agent runtime plus helper tooling |
| `intel-observability` | `intel + observability` | Intel-aware agent runtime plus dashboards and metrics |
| `intel-full` | `intel + tools + observability` | Intel-aware runtime with helper tooling and visibility |

## How presets interact with profiles

Presets expand into profiles.
Profiles then expand into modules.

This means you can:
- use only a preset
- use only profiles
- combine presets and profiles

Examples:

### Use only a preset

```bash
aoa-up --preset agent-full
```

### Inspect preset expansion

```bash
aoa-preset-profiles --preset agent-full --paths
aoa-profile-modules --preset agent-full --paths
aoa-profile-endpoints --preset agent-full
```

### Combine a preset with an extra profile

```bash
aoa-up --preset agent-tools --profile observability
```

### Use comma-separated preset form

```bash
aoa-up --preset agent-tools,intel-observability
```

## Resolution rules

- presets are resolved in the order you declare them
- preset-expanded profiles are appended in that order
- direct `--profile` arguments are appended after preset expansion
- duplicate profiles are kept only once, at first appearance
- duplicate modules are kept only once, at first appearance

## Recommended introspection flow

Before launching a preset:

```bash
aoa-preset-profiles --preset agent-full --paths
aoa-profile-modules --preset agent-full --paths
aoa-profile-endpoints --preset agent-full
aoa-render-services --preset agent-full
aoa-render-config --preset agent-full --write /tmp/abyss-agent-full.rendered.yml
```

Treat rendered output as potentially secret-bearing.
