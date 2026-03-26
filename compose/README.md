# compose layout

The new stack uses small compose modules, named profiles, and named presets.

## Modules

- `modules/10-storage.yml`
- `modules/20-orchestration.yml`
- `modules/30-local-inference.yml`
- `modules/31-intel-inference.yml`
- `modules/40-llm-gateway.yml`
- `modules/41-agent-api.yml`
- `modules/42-agent-api-intel.yml`
- `modules/50-speech.yml`
- `modules/51-browser-tools.yml`
- `modules/60-monitoring.yml`

`41-agent-api.yml` may consume a public-safe return policy file from `Configs/agent-api/return-policy.yaml`.

## Profiles

- `profiles/core.txt`
- `profiles/agentic.txt`
- `profiles/intel.txt`
- `profiles/tools.txt`
- `profiles/observability.txt`

A profile is only a list of module filenames in activation order.

## Presets

- `presets/agent-tools.txt`
- `presets/agent-observability.txt`
- `presets/agent-full.txt`
- `presets/intel-tools.txt`
- `presets/intel-observability.txt`
- `presets/intel-full.txt`

A preset is a list of profile names in activation order.

## Rule

New capability should arrive as:
1. a module
2. optionally a profile inclusion
3. optionally a preset inclusion for a common operating bundle
4. corresponding docs and lifecycle notes

Not as a silent growth of one giant compose file.
