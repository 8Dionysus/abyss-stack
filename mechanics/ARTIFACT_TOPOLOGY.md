# Mechanics Artifact Topology

This file defines where runtime mechanic artifacts should live as the flat
source surface becomes more convex.

## Current rule

The first wave created route homes. The second wave may move a flat artifact
family when the package owner is clear and validators, tests, generated
companions, and route links move at the same time.

Old noisy file names with wave, seed, phase, or raw version scaffolding should
land under package-local `legacy/` first. Legacy is provenance and containment,
not trash and not the new active route.

## Placement lanes

| Artifact kind | Current default | Future package home when clearly local |
|---|---|---|
| operator docs | `docs/` | `mechanics/<package>/docs/` for package-owned active docs, or `mechanics/<package>/legacy/raw/` for old raw docs |
| runtime scripts | `scripts/` | `mechanics/<package>/legacy/artifacts/scripts/` while old names remain legacy |
| schemas | `schemas/` | `mechanics/<package>/docs/<contract>/` for active package-local contracts, or `mechanics/<package>/legacy/artifacts/schemas/` when the family is contained |
| examples | `examples/` | `mechanics/<package>/docs/<contract>/` for active package-local public examples, or `mechanics/<package>/legacy/artifacts/examples/` with validator updates |
| generated capsules | `generated/` | `mechanics/<package>/legacy/artifacts/generated/` when the source builder moves too |
| config templates | `config-templates/` | package-local config only when bootstrap and sync know the new path |
| tests | `tests/` | `mechanics/<package>/tests/` for active package-local contract tests, or `mechanics/<package>/legacy/artifacts/tests/` while old test names remain legacy |
| deployed mirror content | `/srv/AbyssOS/abyss-stack/Configs` | never by hand; source sync owns deployed copies |

## Movement contract

Before moving an artifact into a package:

1. Confirm the package is the only honest owner.
2. Update links from `README.md`, `AGENTS.md`, `docs/MECHANICS.md`, and package
   cards as needed.
3. Update `scripts/validate_stack.py` or the narrower validator that names the
   old path.
4. Update deployment sync expectations if the artifact must reach deployed
   `Configs`.
5. Run the narrow validator and report any parity check intentionally skipped.
6. Add or update `PROVENANCE.md`, `legacy/INDEX.md`, and `legacy/DISTILLATION_LOG.md`
   when old names are moved for lineage rather than active-route promotion.

## Stop-lines

- Do not hide runtime scripts where operator wrappers cannot find them.
- Do not move public-safe examples into a package while validators still read
  the root `examples/` path.
- Do not move generated JSON without moving or updating the builder.
- Do not use package placement to claim live availability.
- Do not copy stronger owner doctrine into this repository; route to the owner.
