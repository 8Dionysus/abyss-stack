# service templates

This directory stores source-managed build contexts for lightweight runtime
helper services that belong to the stack body.

Bootstrap behavior:

- `scripts/aoa-bootstrap-configs` seeds these trees into
  `${AOA_STACK_ROOT}/Services/`
- default mode is non-destructive and keeps existing runtime files
- use `scripts/aoa-bootstrap-configs --force` when you intentionally want the
  repo-managed service trees to refresh an existing runtime

Current source-managed service trees:

- `docs-api/`
- `langchain-api/`
- `litellm/`
- `qwen3-tts-api/`
- `route-api/`
- `tts_router/`

Intentionally still runtime-only:

- `aoa-browser/`
  - current contract is a prebuilt local image plus browser payload under
    `${AOA_STACK_ROOT}/Services/aoa-browser/ms-playwright`
