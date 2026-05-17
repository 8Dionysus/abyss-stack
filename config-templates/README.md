# config templates

This directory stores public-safe runtime config templates.

These files are not the live runtime configs themselves.
They are source-managed templates that can be copied into the deployed runtime tree with:

```bash
scripts/aoa-bootstrap-configs
```

## Intent

- keep examples public-safe
- reduce first-run friction
- avoid mixing real secrets into git
- make the deployed runtime shape more obvious

## Current template families

- `Configs/agent-api/`
- `Configs/federation/`
- `Configs/monitoring/`
- `Configs/tts/`
- `Configs/ollama/`
- `Configs/tos-graph/`
- `Configs/rag/`
- `Services/docs-api/`
- `Services/aoa-browser/`
- `Services/babelvox-tts-api/`
- `Services/langchain-api/`
- `Services/litellm/`
- `Services/qwen3-tts-api/`
- `Services/rag-api/`
- `Services/rerank-api/`
- `Services/route-api/`
- `Services/tos-graph/`
- `Services/tts_router/`

These `Services/*` entries are source-managed build contexts for lightweight
runtime helper services. They are bootstrapped into the deployed runtime tree by
`scripts/aoa-bootstrap-configs`.

`Configs/federation/upstream-compatibility-bridge.json` is the public-safe
runtime bridge data file for sibling-owner names that still need compatibility
handling. Layer YAML files should keep clean local required files and let that
bridge carry upstream legacy identifiers.

The `Configs/agent-api/` family currently carries the public-safe runtime
templates for:

- `return-policy.yaml`
- `governed-execution-policy.yaml`
- `governed-canary-catalog.json`

The `Configs/rag/` family carries public-safe RAG source registry, agentic graph,
and DAG job manifests for the `rag-api` service. It describes where mounted
runtime source mirrors live inside the container; it does not store embeddings,
private captures, or generated Qdrant payloads in git.

`aoa-browser` is now source-managed here as a lightweight browser-helper build
context. The Playwright browser payload under
`/srv/AbyssOS/abyss-stack/Services/aoa-browser/ms-playwright/` remains runtime-only.
