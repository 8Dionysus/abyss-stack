# Rendering Artifact Manifests

This directory holds OS Abyss artifact bundle manifests for public-safe rendered
runtime config outputs.

The manifests are source inputs for `abyss-machine` artifact verification. They
bind rendered config files under `dist/abyss-stack-runtime-config/` to ABI,
SBOM, and SLSA/in-toto sidecars.

Validation route:

```bash
python mechanics/config-projection/parts/rendering/scripts/validate_abyss_machine_runtime_config_bundle.py
```

Generated subjects and sidecars are written under ignored `dist/` paths and do
not become source truth.
