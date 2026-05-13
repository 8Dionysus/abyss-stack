# Experience Runtime Archive Classification

This file classifies the preserved experience-runtime family without promoting
it into active runtime topology.

## Verdict

The family remains archive-only.

The preserved schemas, examples, raw docs, and tests are useful lineage, but no
current `abyss-stack` service, storage path, operator command, or validator
consumes them as active runtime contracts. Promotion without a concrete
consumer would make old wave/seed-era names look current.

## Families

| Family | Raw docs | Artifact examples and schemas | Current verdict |
|---|---|---|---|
| Adoption transport | `ADOPTION_*` docs | `adoption_*` records and jobs | archive-only until an adoption runtime service consumes them |
| Governance and council | `GOVERNANCE_*`, `COUNCIL_*`, `VETO_*`, `STAY_*`, `APPEAL_*`, `CONSTITUTION_*` docs | governance and constitution records | archive-only; meaning belongs to stronger owner repos |
| Release and deployment | `FIRST_RELEASE_*`, `ASSISTANT_RELEASE_*`, `DEPLOYMENT_*`, `ROLLBACK_*`, `INSTALLATION_*` docs | release lifecycle, deployment, rollback, canary, and watchtower records | archive-only until a concrete release worker or storage route exists |
| Federation and knowledge transport | `FEDERATION_HARVEST_*`, `KAG_PROMOTION_*`, `TOS_DOSSIER_*`, `PATTERN_REGISTRY_*` docs | federation harvest, KAG promotion, ToS dossier, and pattern registry records | archive-only; sibling repo authority remains stronger |
| Office and operator mesh | `OFFICE_*`, `OPERATOR_CONSOLE_*`, `HANDOFF_GRAPH_*`, `SERVICE_MESH_*`, `CANARY_*` docs | office mesh, console queue, handoff graph, service mesh, and smoke records | archive-only until one operator-facing runtime command consumes them |
| Storage migration | runtime storage and migration plans | `runtime_storage_migration_v1` | archive-only until storage layout migration tooling consumes it |

## Promotion Gate

Promote only one family at a time, and only when all of these are true:

- a concrete `abyss-stack` service, storage path, or operator command consumes it
- active names are rewritten away from old wave, seed, and raw version topology
- examples, schemas, tests, docs, and validators move together
- stronger owner boundaries are written before runtime adoption
- this classification and `INDEX.md` keep the lineage link

Until then, `legacy/artifacts/` and `legacy/raw/` are the correct homes.
