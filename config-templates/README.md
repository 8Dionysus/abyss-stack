# config templates

This directory stores public-safe runtime config templates.

These files are not the live runtime configs themselves.
They are source-managed templates that can be copied into the deployed runtime
tree through the bootstrap route in [AGENTS](AGENTS.md#bootstrap-route).

## Intent

- keep examples public-safe
- reduce first-run friction
- avoid mixing real secrets into git
- make the deployed runtime shape more obvious

## Current template families

- `Configs/agent-api/`
- `Configs/federation/`
- `Configs/monitoring/`
- `Configs/ovms/`
- `Configs/tts/`
- `Configs/ollama/`
- `Configs/llama-swap/`
- `Configs/tos-graph/`
- `Configs/rag/`
- `Services/docs-api/`
- `Services/aoa-browser/`
- `Services/babelvox-tts-api/`
- `Services/langchain-api/`
- `Services/litellm/`
- `Services/llama-swap/`
- `Services/qwen3-tts-api/`
- `Services/rag-api/`
- `Services/rerank-api/`
- `Services/route-api/`
- `Services/tos-graph/`
- `Services/tts_router/`

These `Services/*` entries are source-managed build contexts for lightweight
runtime helper services. They are bootstrapped into the deployed runtime tree
through the bootstrap route named in [AGENTS](AGENTS.md#bootstrap-route).

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
`rag-api` also exposes a redacted `/semantic-inventory` read route for
Postgres schema/freshness, Neo4j label/relationship/freshness, RAG source, and
agentic graph shape. That route stores no database rows, graph properties,
source documents, or credentials.

The `Configs/monitoring/` family carries Prometheus, Alertmanager, Grafana,
Loki, and Alloy public-safe templates. Loki stores logs in a runtime volume;
Alloy reads rootless Podman journald entries and keeps a file-log fallback for
hosts that use a file log driver, forwarding both to Loki for LogQL through
Grafana. Alloy also accepts OTLP traces for forwarding to Tempo. When rootless
Podman storage is relocated, render the monitoring profile with
`AOA_PODMAN_CONTAINERS_ROOT` pointing at that containers root; otherwise the
`aoa-*` shell route derives it from `AOA_RUNTIME_USER`.
`route-api` reads Grafana datasource provisioning files as a bounded
`/observability/datasources` inventory route; it exposes datasource identity,
type, access, default status, and source file freshness without secure JSON,
tokens, passwords, or raw dashboard settings.

`Services/langchain-api/` writes redacted runtime thread, checkpoint, and trace
inventory to `${AOA_STACK_ROOT}/Logs/langgraph-inventory` when bootstrapped and
run through `41-agent-api.yml`; this is runtime evidence, not source truth.

`aoa-browser` is now source-managed here as a lightweight browser-helper build
context. The Playwright browser payload under
`/srv/AbyssOS/abyss-stack/Services/aoa-browser/ms-playwright/` remains runtime-only.
