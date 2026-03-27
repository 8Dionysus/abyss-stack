# ollama runtime config notes

The current stack mounts `${AOA_STACK_ROOT}/Configs/ollama` into the Ollama container as `/cfg`.

This directory carries optional local runtime helper material for Ollama-backed paths.

Current posture:
- chat runs should use `qwen3.5:9b` directly on the Ollama side
- Intel/OVMS owns the Qwen3 embedding line
- Ollama fallback embeddings should use `nomic-embed-text` directly
- runtime startup warms `qwen3.5:9b` after `aoa-up` when local inference is selected
- the default keep-alive is `30m`, so the chat model should stay resident across normal short idle periods

Keep these files local-runtime focused.
Do not put secrets here.
