# Federation Seams Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Sync wrapper | `parts/sync-wrapper/` | `scripts/aoa-sync-federation-surfaces` |
| Federation checks | `parts/federation-checks/` | `scripts/aoa-federated-check`; legacy harvest worker docs now route through `mechanics/experience-runtime/legacy/raw/FEDERATION_HARVEST_WORKER.md` |
| Memo seam | `parts/memo-seam/` | `docs/MEMO_RUNTIME_SEAM.md` |
| Eval seam | `parts/eval-seam/` | `docs/EVAL_RUNTIME_SEAM.md` |
| Playbook seam | `parts/playbook-seam/` | `docs/PLAYBOOK_RUNTIME_SEAM.md` |
| KAG seam | `parts/kag-seam/` | `docs/KAG_RUNTIME_SEAM.md` |
| ToS graph | `parts/tos-graph/` | `docs/TOS_GRAPH_CURATION.md`, `compose/modules/52-tos-graph.yml` |
| RPG runtime | `parts/rpg-runtime/` | `docs/RPG_ROUTE_API_SEAM.md`, `docs/RPG_RUNTIME_COLLECTIONS.md`, `docs/RPG_RUNTIME_BUILDERS.md`, generated collections, package-local tests, `scripts/aoa-rpg-runtime-projection` |

Do not move these parts until owner-boundary links and validators follow.
