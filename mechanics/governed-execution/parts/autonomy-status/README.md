# Autonomy Status

Routes `scripts/aoa-status`,
`mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py`,
and `tests/test_aoa_status_autonomy.py`.

Status readouts are evidence for decisions. They are not autonomous authority.
Old long-horizon and bounded-autonomy runtime artifact names appear here only
through the preserved trial compatibility route.

For `aoa-routing`, a predecessor source-ref mismatch remains degraded unless
the live route-api independently reports the exact receipt-bound
`sdk_canonical` posture, `authorized_live_cutover`, canonical closure, retained
predecessor, trusted subject, and archive-denied G5 authority. This is a
consumer evidence fallback for the autonomy readout; it does not make
route-api or the status command an owner or archival authority.

## Source binding

Parity-aware source selection is fail-closed and owner-qualified:

1. An explicit `AOA_SOURCE_ROOT` is the operator binding and has precedence.
   If it is invalid, the resolver does not silently fall through to another
   checkout.
2. When the helper is executed from source, its own root is accepted only when
   the `abyss-stack` owner markers and source shape are present.
3. The deployed `Configs` projection, `~/src/abyss-stack`, and sibling or
   workspace discovery are not implicit source candidates.

If no valid binding exists, the parity check reports
`source_root_unresolved`. That is a source-input truth gap, not runtime health,
deployment, or semantic acceptance evidence.
