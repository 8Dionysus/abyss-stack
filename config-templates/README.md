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
- `Services/docs-api/`
- `Services/aoa-browser/`
- `Services/langchain-api/`
- `Services/litellm/`
- `Services/qwen3-tts-api/`
- `Services/route-api/`
- `Services/tos-graph/`
- `Services/tts_router/`

These `Services/*` entries are source-managed build contexts for lightweight
runtime helper services. They are bootstrapped into the deployed runtime tree by
`scripts/aoa-bootstrap-configs`.

The `Configs/agent-api/` family currently carries the public-safe runtime
templates for:

- `return-policy.yaml`
- `governed-execution-policy.yaml`
- `governed-canary-catalog.json`

`aoa-browser` is now source-managed here as a lightweight browser-helper build
context. The Playwright browser payload under
`/srv/AbyssOS/abyss-stack/Services/aoa-browser/ms-playwright/` remains runtime-only.
