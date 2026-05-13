# Machine Fit Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Reference platform | `parts/reference-platform/` | `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md`, `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md`, `parts/host-facts/` |
| Host facts | `parts/host-facts/` | `scripts/aoa-host-facts`, `mechanics/diagnostic-spine/docs/DOCTOR.md`, host-facts schema and public examples |
| Machine bridge | `parts/machine-bridge/` | `scripts/aoa-machine-bridge`, bridge docs, schema, example, and focused tests |
| Machine fit | `parts/fit-record/` | `scripts/aoa-machine-fit`, `mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md`, fit-record schema and example |
| Platform adaptation | `parts/platform-adaptations/` | `scripts/aoa-platform-adaptation`, `mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md`, platform-adaptation schema and example |
| Inference tuning | `parts/inference-tuning/` | `compose/tuning/`, `mechanics/machine-fit/parts/inference-tuning/docs/model-cards/`, `mechanics/machine-fit/parts/inference-tuning/docs/MODEL_PROFILES.md` |
| Windows bridge | `parts/windows-bridge/` | Windows bridge, setup, and performance docs |

Reference-platform docs, machine bridge, host facts, fit records, platform
adaptations, Windows bridge docs, and inference tuning are active package-local
contracts. Root scripts remain operator-facing wrappers.
