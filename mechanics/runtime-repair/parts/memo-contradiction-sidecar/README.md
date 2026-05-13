# Memo Contradiction Sidecar

Routes `scripts/aoa-run-memo-contradiction-integrity`,
`mechanics/runtime-repair/parts/memo-contradiction-sidecar/aoa_memo_contradiction_integrity.py`,
and the focused sidecar test.

The sidecar checks integrity evidence. It does not own memo meaning.
Clean local runtime evidence lives under the `memo-contradiction-rerun` route.
Older memo IDs and runtime log paths are accepted only as upstream/historical
compatibility inputs routed through
`mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`.
