# service templates

This directory stores source-managed build contexts for lightweight runtime
helper services that belong to the stack body.

Bootstrap behavior:

- `scripts/aoa-bootstrap-configs` populates these trees into
  `${AOA_STACK_ROOT}/Services/`
- default mode is non-destructive and keeps existing runtime files
- use `scripts/aoa-bootstrap-configs --force` when you intentionally want the
  repo-managed service trees to refresh an existing runtime

Current source-managed service trees:

- `aoa-browser/`
- `babelvox-tts-api/`
- `docs-api/`
- `langchain-api/`
- `litellm/`
- `llama-swap/`
- `qwen3-tts-api/`
- `rag-api/`
- `rerank-api/`
- `route-api/`
- `tos-graph/`
- `tts_router/`

Intentionally still runtime-only:

- `aoa-browser/ms-playwright/`
  - Playwright browser payload is machine-local runtime state under
    `${AOA_STACK_ROOT}/Services/aoa-browser/ms-playwright`
