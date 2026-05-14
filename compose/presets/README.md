# compose presets

Presets are named bundles of profiles.

They are the layer above composition:
- modules are the atomic runtime pieces
- profiles are named stacks of modules
- presets are named stacks of profiles

The conservative working substrate is `profiles/substrate.txt`. It stays a
profile so operators can layer local-worker, fallback-gateway, federation,
tools, or observability deliberately.

## Format

Each preset file is a plain text file listing profile names in activation order.
Comments and empty lines are allowed.

Example:

```text
substrate
local-worker
tools
observability
```

## Current presets

- `agent-federation`
- `agent-tools`
- `agent-observability`
- `agent-full`
- `intel-federation`
- `intel-tools`
- `intel-observability`
- `intel-full`

Agent presets resolve through `substrate + local-worker`. Intel presets resolve
through `substrate + intel-worker`. The older broad `agentic` and `intel`
profiles remain runnable compatibility routes, not the preset substrate.

## Usage

```bash
aoa-preset-profiles --preset agent-full
aoa-profile-modules --preset agent-full --paths
aoa-profile-endpoints --preset agent-full
aoa-up --preset agent-full
aoa-smoke --with-internal --preset agent-full
```

For the opt-in advisory federation seam:

```bash
aoa-preset-profiles --preset agent-federation --paths
aoa-profile-endpoints --preset agent-federation
aoa-up --preset agent-federation
```
