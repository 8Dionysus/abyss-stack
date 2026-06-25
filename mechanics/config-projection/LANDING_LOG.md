# Config Projection Landing Log

## 2026-05-07 - Initial package landing

Created the config-projection package as the route home for public-safe
templates, env examples, rendering, bootstrap, sync, and deployed `Configs`
projection.

Validation route: `python scripts/validate_nested_agents.py` and
`python scripts/validate_stack.py`.

## 2026-05-13 - Wrapper/backend topology

Kept stable root command wrappers while moving bootstrap, sync, and render
implementation bodies into package parts.

Validation route: `python scripts/validate_stack.py`, shell syntax checks, and
GitHub repo validation.

## 2026-05-13 - Package card completion

Added package-local `DIRECTION.md`, `PROVENANCE.md`, `ROADMAP.md`, and this
landing log so future projection changes have the same route-card spine as the
rest of `mechanics/`.

## 2026-05-13 - Residual frontier alignment

Confirmed the remaining frontier should advance through source-first synthetic
parity before live runtime sync. Packet closeout now uses synthetic roots when
runtime evidence is needed, but the source checkout still treats deployed
`Configs` as a projection target rather than source authority.

## 2026-06-24 - Runtime config artifact trust-gate

Extended the rendering artifact bundle lane from sidecar verification into the
full OS Abyss consumer loop: evidence promotion, release-ready registry latest,
materialized subject-store rehearsal, runtime trust-gate allow, revoked-record
denial, and registry-latest read-model checks. Materialized proof stays under
ignored `dist/` and is sanitized to repo-relative references.

Validation route:

```bash
python scripts/ci_gate.py --mode source-fast
python scripts/ci_gate.py --mode release
python mechanics/config-projection/parts/rendering/scripts/validate_abyss_machine_runtime_config_bundle.py
abyss-machine artifacts registry-latest --registry-dir dist/abyss-artifact-registry/abyss-stack-runtime-config --artifact-class abyss_stack_runtime_config_bundle --consumer-intent runtime --source-repo abyss-stack --trust-root-mode host_managed --json
```
