# Machine Fit Parts

| Part | Current source surfaces |
|---|---|
| Reference platform | `docs/REFERENCE_PLATFORM.md`, `docs/REFERENCE_PLATFORM_SPEC.md`, `docs/reference-platform/` |
| Host facts | `scripts/aoa-host-facts`, `docs/DOCTOR.md` |
| Machine bridge | `scripts/aoa-machine-bridge`, `mechanics/machine-fit/docs/MACHINE_BRIDGE.md`, `mechanics/machine-fit/docs/machine-bridge/`, `mechanics/machine-fit/tests/test_machine_bridge_contracts.py` |
| Machine fit | `scripts/aoa-machine-fit`, `docs/MACHINE_FIT_POLICY.md`, `docs/machine-fit/` |
| Platform adaptation | `scripts/aoa-platform-adaptation`, `docs/PLATFORM_ADAPTATION_POLICY.md`, `docs/platform-adaptations/` |
| Inference tuning | `compose/tuning/`, `docs/model-cards/`, `docs/MODEL_PROFILES.md` |

Machine bridge is the first active package-local contract in this mechanic:
the root script remains operator-facing, while the contract docs, schema,
example, and focused tests live with the package.
