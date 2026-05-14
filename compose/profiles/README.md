# compose profiles

Profiles are named runtime selections. They keep service selection visible
without turning every module into the default AbyssOS substrate.

## Rings

| Profile | Ring | Role |
|---|---|---|
| `substrate` | base | storage plus orchestration; the source-owned default |
| `local-worker` | worker | canonical `llama.cpp` plus `langchain-api` path |
| `fallback-gateway` | retained fallback | Ollama plus LiteLLM control and rollback path |
| `core` | compatibility | storage, orchestration, and `llama.cpp` basics for older habits |
| `agentic` | worker bundle | substrate plus canonical local-worker API |
| `intel` | worker bundle | agentic plus reviewed Intel/OVMS embeddings seam |
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
