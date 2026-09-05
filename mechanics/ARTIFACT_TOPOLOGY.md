# Mechanics Artifact Topology

This file defines where runtime mechanic artifacts should live as the flat
source surface becomes more convex.

## Current rule

The initial pass created route homes. Current movement makes package topology
convex: every mechanic has `parts/README.md`, every named part has
`parts/<part>/README.md`, and active package-local artifacts live inside the
owning part.

Historical wave, seed, phase, and retired artifact trees remain recoverable
through exact Git commits and original paths recorded in package provenance.
Keep needed active contracts with their actual consumers; do not create a
current archive tree merely to preserve old names.

## Placement lanes

| Artifact kind | Current default | Package home when clearly local |
|---|---|---|
| operator docs | `docs/` | `mechanics/<package>/docs/` for package-owned prose detail or `mechanics/<package>/parts/<part>/` for current part contracts and routes |
| runtime scripts | stable operator wrappers in `scripts/` | `mechanics/<package>/parts/<part>/` for active implementations and required compatibility runners |
| schemas | `schemas/` | `mechanics/<package>/parts/<part>/schemas/` for active package-local contracts |
| examples | `examples/` | `mechanics/<package>/parts/<part>/examples/` for active package-local public examples |
| generated capsules | `generated/` | `mechanics/<package>/parts/<part>/generated/` with the owning source builder |
| config templates | `config-templates/` | package-local config only when bootstrap and sync know the new path |
| tests | `tests/` | `mechanics/<package>/parts/<part>/tests/` for active package-local contract tests |
| deployed mirror content | `/srv/AbyssOS/abyss-stack/Configs` | never by hand; source sync owns deployed copies |

## Movement contract

Before moving an artifact into a package:

1. Confirm the package is the only honest owner.
2. Update links from `README.md`, `AGENTS.md`, `docs/runtime/MECHANICS.md`, package
   cards, `PARTS.md`, `parts/README.md`, and the part-local `README.md`.
3. Update `scripts/validate_stack.py` or the narrower validator that names the
   old path.
4. Update deployment sync expectations if the artifact must reach deployed
   `Configs`.
5. Run the narrow validator and report any parity check intentionally skipped.
6. Update `PROVENANCE.md` with immutable source recovery and current-owner
   routes when historical files leave the active tree. Preserve history, not
   a mandatory local archive scaffold.

## Stop-lines

- Do not move operator command names out of `scripts/` unless deployment sync,
  runbooks, and validators all move with them.
- Do not hide runtime implementations where the stable operator wrappers cannot
  find them in both source checkout and deployed `Configs` mirror shape.
- Do not move public-safe examples into a package while validators still read
  the old path.
- Do not move generated JSON without moving or updating the builder.
- Do not leave active package-local schemas, examples, generated capsules, or
  focused tests in loose `mechanics/<package>/docs/surfaces`, `generated`, or
  `tests` directories after the owning part exists.
- Do not use package placement to claim live availability.
- Do not copy stronger owner doctrine into this repository; route to the owner.
