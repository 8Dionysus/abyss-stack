# ollama runtime config notes

The current stack mounts `${AOA_STACK_ROOT}/Configs/ollama` into the Ollama container as `/cfg`.

This directory is reserved for optional local runtime material such as:
- helper notes
- future model alias material
- future Modelfile or bootstrap helpers

At the current stage the stack does not require a concrete file here to boot.
