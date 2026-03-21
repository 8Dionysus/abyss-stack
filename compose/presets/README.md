# compose presets

Presets are named bundles of profiles.

They are the layer above composition:
- modules are the atomic runtime pieces
- profiles are named stacks of modules
- presets are named stacks of profiles

## Format

Each preset file is a plain text file listing profile names in activation order.
Comments and empty lines are allowed.

Example:

```text
agentic
tools
observability
```

## Current presets

- `agent-tools`
- `agent-observability`
- `agent-full`
- `intel-tools`
- `intel-observability`
- `intel-full`

## Usage

```bash
aoa-preset-profiles --preset agent-full
aoa-profile-modules --preset agent-full --paths
aoa-profile-endpoints --preset agent-full
aoa-up --preset agent-full
aoa-smoke --with-internal --preset agent-full
```
