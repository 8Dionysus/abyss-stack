# Machine Fit Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Reference platform | `parts/reference-platform/` | `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM.md`, `mechanics/machine-fit/parts/reference-platform/docs/REFERENCE_PLATFORM_SPEC.md`, `parts/host-facts/` |
| Host facts | `parts/host-facts/` | `scripts/aoa-host-facts`, `parts/host-facts/aoa_host_facts.py`, `mechanics/diagnostic-spine/parts/doctor-readiness/docs/DOCTOR.md`, host-facts schema and public examples |
| Machine bridge | `parts/machine-bridge/` | `scripts/aoa-machine-bridge`, `parts/machine-bridge/aoa_machine_bridge.py`, bridge docs, schema, example, and focused tests |
| Machine fit | `parts/fit-record/` | `scripts/aoa-machine-fit`, `parts/fit-record/aoa_machine_fit.py`, `mechanics/machine-fit/parts/fit-record/docs/MACHINE_FIT_POLICY.md`, fit-record schema and example |
| Platform adaptation | `parts/platform-adaptations/` | `scripts/aoa-platform-adaptation`, `parts/platform-adaptations/aoa_platform_adaptation.py`, `mechanics/machine-fit/parts/platform-adaptations/docs/PLATFORM_ADAPTATION_POLICY.md`, platform-adaptation schema and example |
| Inference tuning | `parts/inference-tuning/` | `compose/tuning/`, `mechanics/machine-fit/parts/inference-tuning/docs/model-cards/`, `mechanics/machine-fit/parts/inference-tuning/docs/MODEL_PROFILES.md` |
| Windows bridge | `parts/windows-bridge/` | `scripts/aoa.ps1`, `scripts/aoa-doctor-win.ps1`, `scripts/aoa-bootstrap-wsl.ps1`, part-local PowerShell backends, Windows bridge, setup, and performance docs |

Reference-platform docs, machine bridge, host facts, fit records, platform
adaptations, Windows bridge docs, and inference tuning are active package-local
contracts. Root scripts remain operator-facing wrappers.
