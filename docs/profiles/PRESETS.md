# PRESETS

Presets are named bundles of profiles.

They exist one layer above profile composition:
- modules are the atomic runtime pieces
- profiles are named stacks of modules
- presets are named stacks of profiles

The default working substrate is a profile, not a preset: use `substrate` for
the conservative OS base and layer workflows, worker, fallback, or helper
profiles explicitly.

## Why presets exist

Once multi-profile composition became possible, certain combinations turned into common operating modes.
Presets give these combinations stable names, so you do not have to repeat long profile lists for every command.

## Current presets

| preset | resolves to | intended use |
|---|---|---|
| `agent-federation` | `substrate + local-worker + federation` | generic local agent runtime plus the opt-in advisory federation and retrieval seam |
| `agent-tools` | `substrate + local-worker + tools` | local agent runtime with speech and browser tooling |
| `agent-observability` | `substrate + local-worker + observability` | local agent runtime plus dashboards and metrics |
| `agent-full` | `substrate + local-worker + tools + observability` | generic local agent runtime with helpers and visibility |
| `intel-federation` | `substrate + intel-worker + federation` | Intel-aware agent runtime plus the opt-in advisory federation and retrieval seam |
| `intel-tools` | `substrate + intel-worker + tools` | Intel-aware agent runtime plus helper tooling |
| `intel-observability` | `substrate + intel-worker + observability` | Intel-aware agent runtime plus dashboards and metrics |
| `intel-full` | `substrate + intel-worker + tools + observability` | Intel-aware runtime with helper tooling and visibility |

The federation presets stay opt-in.
They do not promote the advisory seam into the default runtime path or the
default promoted presets.
The `workflows` profile also stays opt-in. Current presets do not start n8n;
add `--profile workflows` only when workflow automation is deliberately part of
the run.

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

### Use the opt-in advisory federation seam

```bash
aoa-preset-profiles --preset agent-federation --paths
aoa-profile-endpoints --preset agent-federation
aoa-up --preset agent-federation
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
aoa-up --preset agent-full --profile workflows
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
aoa-doctor --preset agent-full
aoa-preset-profiles --preset agent-full --paths
aoa-profile-modules --preset agent-full --paths
aoa-profile-endpoints --preset agent-full
aoa-render-services --preset agent-full
aoa-render-config --preset agent-full --write /tmp/abyss-agent-full.rendered.yml
```

Treat rendered output as potentially secret-bearing.

## Preset-aware smoke patterns

Generic full bundle:

```bash
aoa-up --preset agent-full
aoa-smoke --with-internal --preset agent-full
```

Intel-aware full bundle:

```bash
aoa-doctor --preset intel-full
aoa-up --preset intel-full
aoa-smoke --with-internal --preset intel-full
```
