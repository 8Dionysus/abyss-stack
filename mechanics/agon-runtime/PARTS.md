# Agon Runtime Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Active route | `parts/active-route/` | `README.md`, `DIRECTION.md`, `PROVENANCE.md` |
| Legacy runtime kernels | `parts/legacy-runtime-kernels/` | `legacy/raw/AGON_*`, `legacy/artifacts/config/agon_*.seed.json`, `legacy/artifacts/generated/agon_*.min.json`, `legacy/artifacts/examples/agon_*`, `legacy/artifacts/scripts/*agon*`, `legacy/artifacts/schemas/agon-*.schema.json`, `legacy/artifacts/tests/test_agon_*`, `legacy/artifacts/manifests/recurrence/` |

Legacy file names are intentionally preserved for provenance. New active files
should receive quieter package-local names when they graduate out of `legacy`.
