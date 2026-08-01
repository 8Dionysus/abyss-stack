# Federation Seams Parts

| Part | Route | Current source surfaces |
|---|---|---|
| Sync wrapper | `parts/sync-wrapper/` | `scripts/aoa-sync-federation-surfaces`, the exact-trust non-canonical `aoa-routing-canary`, and the receipt-bound canonical `aoa-routing-cutover`; validates source freshness, subject-store bytes, public-release/runtime admission, reversible activation, and explicit producer posture |
| Federation checks | `parts/federation-checks/` | `scripts/aoa-federated-check`, `parts/federation-checks/aoa_federated_check.py`, route-api routing ABI/provenance/trust closure, active compatibility bridge at `parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`, active detailed inventory at `parts/federation-checks/docs/UPSTREAM_COMPATIBILITY_DETAIL.md`; archived harvest worker docs now route through `mechanics/experience-runtime/PROVENANCE.md` |
| Memo seam | `parts/memo-seam/` | `mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md`, C20 content-minimized active-organ runtime delivery receipt, ER4/ER5 runtime and backup erasure owner-extension schema, positive/negative examples, and focused tests |
| Eval seam | `parts/eval-seam/` | `mechanics/federation-seams/parts/eval-seam/docs/EVAL_RUNTIME_SEAM.md` |
| Playbook seam | `parts/playbook-seam/` | `mechanics/federation-seams/parts/playbook-seam/docs/PLAYBOOK_RUNTIME_SEAM.md` |
| KAG runtime | `parts/kag-seam/` | trust-admitted membership-bound owner-family composition state, SQLite/FTS, Qdrant and Neo4j adapters, retrieval eval, receipts, `scripts/aoa-kag-runtime-family`, `scripts/aoa-kag-runtime-projection`, `scripts/aoa-kag-runtime-eval`, and `docs/KAG_RUNTIME_SEAM.md` |
| ToS graph | `parts/tos-graph/` | `scripts/tos-up`, `scripts/aoa-tos-graph`, `parts/tos-graph/tos_up.sh`, `parts/tos-graph/aoa_tos_graph.sh`, `mechanics/federation-seams/parts/tos-graph/docs/TOS_GRAPH_CURATION.md`, `compose/modules/52-tos-graph.yml` |
| RPG runtime | `parts/rpg-runtime/` | RPG route/frontend/collection/builder docs, `mechanics/federation-seams/parts/rpg-runtime/docs/RPG_RUNTIME_MATERIALIZATION_PACKET.md`, schemas, examples, generated collections, package-local tests, `scripts/aoa-rpg-runtime-projection`, `parts/rpg-runtime/aoa_rpg_runtime_projection.py` |

These parts are advisory runtime-consumption surfaces. Keep owner-boundary links
and validators aligned when any route moves.
