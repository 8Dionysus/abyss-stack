# Script Topology

`abyss-stack` scripts are a runtime command surface. Root operator wrappers stay
stable because deployment sync copies them into deployed `Configs/scripts/`.
Mechanic packages own implementation meaning, while root `scripts/` owns
stable entrypoint names and bridge contracts.

## Families

| Family | Paths | Owner | Posture |
|---|---|---|---|
| root route docs | `scripts/AGENTS.md`, `scripts/README.md` | `scripts/` route card | source route |
| root operator wrappers | `scripts/aoa-*`, `scripts/aoa.ps1` | owning mechanic parts | operator-facing, side effects depend on command |
| root validation entrypoints | `scripts/validate_*`, `scripts/*decision*`, `scripts/release_check.py`, `scripts/ci_gate.py` | root validation topology | source validation |
| focused validator modules | `scripts/validators/*.py` | validation topology | owner-surface implementation modules behind root validators |
| diagnostic generated helpers | `scripts/build_diagnostic_surface_catalog.py`, `scripts/validate_diagnostic_surface_catalog.py` | diagnostic spine | generated/read-model validation |
| MCP service scripts | `mcp/services/*/scripts/*.py` | service-local route card | package-local access-plane validation/run |
| quest helpers | `quests/scripts/*.py` | quest surface | source/generated quest support |
| inference pilot compatibility runners | `mechanics/inference-pilots/parts/local-trials/compatibility-runners/*`, `mechanics/inference-pilots/parts/quiet-bridge-commands/runners/*` | inference-pilots parts | active runner surface behind quiet bridge commands |

## Side-Effect Law

- Operator wrappers may mutate runtime only when their flags, route cards, and
  backend docs make the action explicit.
- Validation entrypoints should not mutate source except generated builders
  when run without `--check`.
- MCP service scripts expose stdio access planes and package release checks;
  they must not promote sibling-owned truth.
- Archived scripts remain provenance only; active command wrappers must execute
  package-local runner surfaces.

## Inventory

`script_inventory.json` records script families, owner surfaces, source truth,
reads, writes, side effects, validation lane, CI inclusion, focused test target,
and disposition. It is descriptive; command sequences stay in
`validation_lanes.json`.
