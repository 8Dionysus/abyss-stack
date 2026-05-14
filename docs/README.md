# docs

`docs/` is the repository-wide documentation layer for `abyss-stack`.
It routes source-checkout readers, operators, and maintainers to the owning
surface without turning root docs into package-local runtime doctrine.

Mechanic-owned doctrine belongs under `mechanics/<package>/` or the relevant
`mechanics/<package>/parts/<part>/` route. Live AbyssOS runtime state belongs
under `/srv/AbyssOS/abyss-stack`, not in this source checkout.

## Districts

| District | Owns | Start |
|---|---|---|
| [routes](routes/README.md) | route-mode law, audit and review entry contracts | [START_HERE_ROUTE_CONTRACT](routes/START_HERE_ROUTE_CONTRACT.md) |
| [runtime](runtime/README.md) | runtime topology, service catalog, path and storage contracts | [ARCHITECTURE](runtime/ARCHITECTURE.md) |
| [install](install/README.md) | source-checkout bootstrap and first-run flow | [DEPLOYMENT](install/DEPLOYMENT.md) |
| [operations](operations/README.md) | lifecycle, runbook, backup/restore, security posture | [RUNBOOK](operations/RUNBOOK.md) |
| [profiles](profiles/README.md) | profiles, presets, profile recipes | [PROFILES](profiles/PROFILES.md) |
| [governance](governance/README.md) | branch, release, and questbook integration routes | [BRANCH_POLICY](governance/BRANCH_POLICY.md) |
| [decisions](decisions/README.md) | durable rationale for topology and workflow choices | [TEMPLATE](decisions/TEMPLATE.md) |
| [legacy](legacy/README.md) | preserved old guidance and migration references | [MIGRATION_FROM_OLD](legacy/MIGRATION_FROM_OLD.md) |

## Start Here

- Repository form: [root DESIGN](../DESIGN.md),
  [root DESIGN.AGENTS](../DESIGN.AGENTS.md), [root AGENTS](../AGENTS.md), then
  [runtime/ARCHITECTURE](runtime/ARCHITECTURE.md).
- Source/install: [runtime/PATHS](runtime/PATHS.md), then
  [install/DEPLOYMENT](install/DEPLOYMENT.md) and
  [install/FIRST_RUN](install/FIRST_RUN.md).
- Live operation: [operations/RUNBOOK](operations/RUNBOOK.md), then
  [scripts/README](../scripts/README.md) and the owning mechanic package.
- Profile selection: [profiles/PROFILES](profiles/PROFILES.md),
  [profiles/PRESETS](profiles/PRESETS.md), then
  [profiles/PROFILE_RECIPES](profiles/PROFILE_RECIPES.md).
- Review and release: [routes/AUDIT](routes/AUDIT.md),
  [governance/RELEASING](governance/RELEASING.md), and
  [decisions](decisions/README.md).

See [AGENTS.md](AGENTS.md) for editing rules.
