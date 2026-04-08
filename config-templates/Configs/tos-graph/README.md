# tos-graph config

This directory stores the public-safe config template for the preview-first ToS
graph helper.

Bootstrapped runtime path:

- `${AOA_STACK_ROOT}/Configs/tos-graph/config.yaml`

Runtime-only secret-bearing env file:

- `${AOA_STACK_ROOT}/Secrets/Configs/tos-graph.env`

The helper stays route-first, localhost-only, and read-first in this slice.
Keep canonical ToS authority in `Tree-of-Sophia`; do not place credentials,
write-enable defaults, or machine-local paths in this template.
