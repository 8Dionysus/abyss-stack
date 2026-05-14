# runtime

`docs/runtime/` owns repository-wide runtime topology and source/runtime path
contracts.

| Surface | Role |
|---|---|
| [ARCHITECTURE](ARCHITECTURE.md) | concrete runtime structure |
| [SERVICE_CATALOG](SERVICE_CATALOG.md) | compose module and service map |
| [PATHS](PATHS.md) | source checkout, deployed runtime, and sibling-root path contract |
| [STORAGE_LAYOUT](STORAGE_LAYOUT.md) | deployed runtime storage layout |
| [MECHANICS](MECHANICS.md) | docs-side bridge into `mechanics/` |

Use this district for runtime-wide shape. Use `mechanics/<package>/` when a
specific runtime move owns the details.
