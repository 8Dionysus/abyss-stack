# Federation Effective Runtime Inputs

- Decision ID: ABYSS-STACK-D-0064
- Status: accepted
- Date: 2026-06-04
- Owner surface: `mechanics/federation-seams/`

## Index Metadata

- Original date: 2026-06-04
- Surface classes: validation topology, runtime route contract
- Stack lanes: source checkout, runtime mirror, release/tooling
- Mechanic parents: federation-seams
- Guard families: federation surface, route-api closure status, sync parity
- Posture: accepted consumer-contract boundary

## Context

`abyss-stack` federation mirrors use source-owned allowlists in
`config-templates/Configs/federation/*.yaml`. Some runtime inputs also come
from `upstream-compatibility-bridge.json`: `aoa-evals` memo rerun examples keep
upstream-published names, and `aoa-playbooks` automation plans still read an
upstream file named `playbook_automation_seeds.json`.

The sync wrapper and layout check already treated those bridge-managed files as
runtime-critical. `route-api` loaded them too, but its layer status only exposed
the yaml `required_files`. That made the status surface less honest than the
runtime loader and made future audits repeat the same yaml-versus-bridge
question.

## Options considered

- Put every bridge-managed upstream file back into the layer yaml allowlist.
- Keep bridge-managed files only as implicit loader details.
- Keep clean layer yaml contracts, but make `route-api` and validators report
  the effective runtime input set: yaml refs plus explicit bridge refs.

## Decision

Keep compatibility-owned upstream names in `upstream-compatibility-bridge.json`,
not in the clean layer yaml contracts.

`route-api` layer status now reports effective required files for bridge-backed
runtime inputs. `scripts/validators/federation_surface.py` protects the
runtime-loaded file matrix across all federation layers, while bridge-specific
legacy names remain guarded by the upstream compatibility bridge and its legacy
index.

## Rationale

The yaml files should describe each active layer contract without reabsorbing
legacy upstream names. The bridge config is the correct boundary for names that
remain because a stronger owner has not yet published a clean replacement.

At the same time, runtime status must show every file the consumer actually
needs. Reporting only yaml refs would make `/status` a weaker diagnostic
surface than the loader and would hide bridge drift until startup or endpoint
resolution failed.

The effective-input route keeps both truths visible: active layer yaml stays
clean, and runtime diagnostics remain complete.

## Consequences

- Positive: `route-api` status now includes bridge-managed eval template refs
  and the playbook automation upstream file as required runtime inputs.
- Positive: federation required-file validation now covers all route-api-loaded
  layer inputs for agents, routing, memo, evals, playbooks, KAG, and ToS.
- Positive: legacy upstream names stay behind
  `upstream-compatibility-bridge.json` instead of returning to active yaml
  contracts.
- Tradeoff: future bridge additions must update route-api effective input
  handling, sync/check handling, layout checks, and validator coverage together.
- Follow-up: if an owner repo publishes clean replacement filenames, retire the
  bridge entry from the legacy index before moving the active runtime contract.

## Source surfaces

- `config-templates/Configs/federation/*.yaml`
- `config-templates/Configs/federation/upstream-compatibility-bridge.json`
- `config-templates/Services/route-api/app/main.py`
- `mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh`
- `mechanics/runtime-lifecycle/parts/layout-install/aoa_check_layout.sh`
- `scripts/validators/federation_surface.py`
- `mechanics/federation-seams/parts/federation-checks/legacy/upstream-compatibility/INDEX.md`

## Follow-up route

Future federation seam changes should audit the effective runtime input set
across yaml, bridge config, sync/check, route-api status, layout checks, and
validator coverage before widening live consumption.
