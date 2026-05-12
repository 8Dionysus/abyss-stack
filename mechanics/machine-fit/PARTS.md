# Machine Fit Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Reference platform | `parts/reference-platform/` | `docs/REFERENCE_PLATFORM.md`, `docs/REFERENCE_PLATFORM_SPEC.md`, `parts/host-facts/` |
| Host facts | `parts/host-facts/` | `scripts/aoa-host-facts`, `docs/DOCTOR.md`, host-facts schema and public examples |
| Machine bridge | `parts/machine-bridge/` | `scripts/aoa-machine-bridge`, bridge docs, schema, example, and focused tests |
| Machine fit | `parts/fit-record/` | `scripts/aoa-machine-fit`, `docs/MACHINE_FIT_POLICY.md`, fit-record schema and example |
| Platform adaptation | `parts/platform-adaptations/` | `scripts/aoa-platform-adaptation`, `docs/PLATFORM_ADAPTATION_POLICY.md`, platform-adaptation schema and example |
| Inference tuning | `parts/inference-tuning/` | `compose/tuning/`, `docs/model-cards/`, `docs/MODEL_PROFILES.md` |

Machine bridge, host facts, fit records, and platform adaptations are active
package-local contracts. Root scripts remain operator-facing wrappers.
