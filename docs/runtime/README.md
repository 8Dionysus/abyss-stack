# runtime

`docs/runtime/` owns repository-wide runtime topology and source/runtime path
contracts.

| Surface | Role |
|---|---|
| [ARCHITECTURE](ARCHITECTURE.md) | concrete runtime structure |
| [SERVICE_CATALOG](SERVICE_CATALOG.md) | compose module and service map |
| [SERVICE_SELECTION](SERVICE_SELECTION.md) | service tiering and optimization posture |
| [service-selection-policy.v1.json](service-selection-policy.v1.json) | machine-readable service posture, current selection, and guard map |
| [service-inventory-2026-05-14.v1.json](service-inventory-2026-05-14.v1.json) | screenshot-derived service inventory baseline |
| [SERVICE_OPTIMIZATION_RESEARCH_2026_05](SERVICE_OPTIMIZATION_RESEARCH_2026_05.md) | current Intel workstation tuning research packet |
| [PATHS](PATHS.md) | source checkout, deployed runtime, and sibling-root path contract |
| [STORAGE_LAYOUT](STORAGE_LAYOUT.md) | deployed runtime storage layout |
| [MECHANICS](MECHANICS.md) | docs-side bridge into `mechanics/` |

Use this district for runtime-wide shape. Use `mechanics/<package>/` when a
specific runtime move owns the details.
