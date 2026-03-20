# compose layout

The new stack uses small compose modules and named profiles.

## Modules

- `modules/10-storage.yml`
- `modules/20-orchestration.yml`
- `modules/30-local-inference.yml`
- `modules/31-intel-inference.yml`
- `modules/40-llm-gateway.yml`
- `modules/41-agent-api.yml`
- `modules/50-speech.yml`
- `modules/51-browser-tools.yml`
- `modules/60-monitoring.yml`

## Profiles

- `profiles/core.txt`
- `profiles/agentic.txt`
- `profiles/intel.txt`
- `profiles/tools.txt`
- `profiles/observability.txt`

A profile is only a list of module filenames in activation order.

## Rule

New capability should arrive as:
1. a module
2. optionally a profile inclusion
3. corresponding docs and lifecycle notes

Not as a silent growth of one giant compose file.
