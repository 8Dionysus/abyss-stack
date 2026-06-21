# Rendering

Routes rendered config/service helpers:
`scripts/aoa-render-config`, `scripts/aoa-render-services`,
`scripts/aoa-preset-profiles`, `scripts/aoa-profile-modules`,
`scripts/aoa-profile-endpoints`, their part-local `aoa_*.sh` backends, and
`mechanics/config-projection/parts/rendering/docs/RENDER_TRUTH.md`.

Rendered outputs are lower authority than their source templates.

`manifests/runtime_config.bundle.json` and
`scripts/validate_abyss_machine_runtime_config_bundle.py` validate the
public-safe rendered `substrate` config as an OS Abyss artifact bundle with
ABI, SBOM, and SLSA/in-toto sidecars under ignored `dist/` paths.
The validator also writes the local bundle registry read-model and rehearses
tamper and terminal-state failures before a rendered config bundle is treated
as release-ready.
