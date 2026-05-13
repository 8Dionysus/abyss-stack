# Federation Seams Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Sync wrapper | `parts/sync-wrapper/` | `scripts/aoa-sync-federation-surfaces`, `parts/sync-wrapper/aoa_sync_federation_surfaces.sh` |
| Federation checks | `parts/federation-checks/` | `scripts/aoa-federated-check`, `parts/federation-checks/aoa_federated_check.py`; legacy harvest worker docs now route through `mechanics/experience-runtime/legacy/raw/FEDERATION_HARVEST_WORKER.md` |
| Memo seam | `parts/memo-seam/` | `mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md` |
| Eval seam | `parts/eval-seam/` | `mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md` |
| Playbook seam | `parts/playbook-seam/` | `mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md` |
| KAG seam | `parts/kag-seam/` | `mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md` |
| ToS graph | `parts/tos-graph/` | `mechanics/federation-seams/parts/tos-graph/docs/TOS_GRAPH_CURATION.md`, `compose/modules/52-tos-graph.yml` |
| RPG runtime | `parts/rpg-runtime/` | RPG route/frontend/collection/builder docs, schemas, examples, generated collections, package-local tests, `scripts/aoa-rpg-runtime-projection`, `parts/rpg-runtime/aoa_rpg_runtime_projection.py` |

These parts are advisory runtime-consumption surfaces. Keep owner-boundary links
and validators aligned when any route moves.
