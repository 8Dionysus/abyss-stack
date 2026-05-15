# compose profiles

Profiles are named runtime selections. They keep service selection visible
without turning every module into the default AbyssOS substrate.

## Rings

| Profile | Ring | Role |
|---|---|---|
| `substrate` | base | storage only; the source-owned default |
| `workflows` | optional workflow automation | n8n plus its storage dependency |
| `local-worker` | worker | canonical `llama.cpp` plus `langchain-api` path |
| `intel-worker` | worker accelerator | canonical local worker plus reviewed OVMS embeddings seam |
| `fallback-gateway` | retained fallback | Ollama plus LiteLLM control and rollback path |
| `core` | compatibility | storage and `llama.cpp` basics for older habits |
| `agentic` | compatibility | older name for storage plus canonical local-worker API |
| `intel` | compatibility | older name for storage plus reviewed Intel worker seam |
| `federation` | advisory seam | localhost federation and retrieval reader |
| `curation` | projection helper | ToS graph helper plus storage substrate |
| `tools` | helper | speech and browser-like helper services |
| `observability` | visibility | monitoring and dashboards |

`44-llamacpp-agent-sidecar.yml` intentionally stays outside this directory's
profiles. It is a pilot sidecar activated by the inference-pilot route or by an
explicit extra compose overlay.

## Rule

If a module is runnable as a normal operator selection, give it a role-named
profile. If a module is a pilot sidecar or one-off overlay, keep it out of
profiles and route it through the owning mechanic.

Current presets should compose `substrate` plus `local-worker` or
`intel-worker` directly. The broad `agentic` and `intel` profiles stay runnable
for compatibility, but they should not become the hidden base for new presets.
`workflows` stays opt-in until an explicit operator or source decision promotes
n8n into a common route.
