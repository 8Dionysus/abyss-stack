# SDK Routing Canary Intake

- Decision ID: ABYSS-STACK-D-0085
- Status: accepted
- Date: 2026-07-25
- Owner surface: `mechanics/federation-seams/parts/sync-wrapper/`

## Index Metadata

- Original date: 2026-07-25
- Surface classes: runtime route contract, artifact consumer admission, health contract
- Stack lanes: source checkout, runtime mirror, operator cutover
- Mechanic parents: federation-seams
- Guard families: artifact trust, routing canary, route-api closure
- Posture: accepted fail-closed non-canonical canary contract

## Context

The SDK routing-producer candidate reached exact stronger-owner artifact
admission: its source ref, subject digest, ABI, SBOM, SLSA/in-toto controls,
durable registry record, and subject store could be checked by
`abyss-machine`. The runtime still had no owner-local way to consume that
evidence.

Using ordinary federation sync would have rebuilt from `aoa-routing` and lost
the SDK producer identity. Copying the SDK bytes directly into the deployed
mirror would have bypassed the runtime owner's required-file, trust, rollback,
and health contracts. Reusing the canonical `runtime` trust posture would also
have falsely implied that the G5 owner switch had already happened.

## Options considered

- Copy the exact SDK files into the live mirror and rely on outer session
  evidence for provenance and rollback.
- Generalize the ordinary federation sync wrapper so it can silently select
  either producer.
- Add a separate exact-input canary adapter and a separate health dimension
  that cannot satisfy canonical closure.

## Decision

Keep ordinary federation sync bound to the current canonical producer. Add
`scripts/aoa-routing-canary` as a separate runtime-consumer adapter for the SDK
candidate.

The adapter requires the exact artifact subject store, full latest-record
`abyss_machine_artifact_trust_gate_v1` verdict for `runtime_canary`, SDK source
ref, canonical predecessor ref, and subject digest. It verifies the subject
ledger and bytes, stable routing ABI identity, durable record, producer
admission, host-managed trust root, and every all-false G5 authority flag.

Every materialization names either `--isolated` or
`--authorized-live-canary`. Replacing an existing tree requires a disjoint
sibling rollback root; live activation also names its owner change record.
Rollback restores the predecessor and preserves the displaced candidate at a
separately named retain root without depending on candidate trust inputs that
may have been revoked, lost, or damaged.

Route-api recognizes `routing_producer_posture:
sdk_g5_candidate_canary`. It may report `canary_ready: true` when the exact
consumer contract passes, but it always keeps `closure_ready: false` for this
posture with an explicit non-canonical reason. Health returns only an
allowlisted trust and producer-admission summary.

## Rationale

A separate adapter makes the transition state legible. The SDK can prove that
it produces bytes the real runtime can load, while the runtime continues to
state honestly that `aoa-routing` is canonical. Exact trust is checked where
consumption occurs, rollback is part of activation rather than a later
promise, and no single green canary result can smuggle the G5 authority switch
into health.

This route also preserves a clean future decision boundary: a later G5 change
must deliberately change producer authority, trust intent, compatibility
window, predecessor posture, and closure law instead of inheriting them from a
canary rehearsal.

## Consequences

- Positive: exact SDK candidate bytes can be rehearsed against the real
  route-api consumer without copying or weakening the canonical ABI.
- Positive: isolated and live-canary activation share one fail-closed contract
  and one recoverable rollback shape.
- Positive: health distinguishes `canary_ready` from canonical
  `closure_ready`.
- Tradeoff: the full trust verdict is stored in the mirror manifest for local
  validation, although service responses expose only an allowlisted summary.
- Tradeoff: an operator-approved live canary remains degraded in ordinary
  health by design.
- Follow-up: gather isolated and then explicitly authorized live canary
  evidence before designing the separate G5 authority-switch receipt.

## Source surfaces

- `mechanics/federation-seams/parts/sync-wrapper/aoa_routing_canary.py`
- `scripts/aoa-routing-canary`
- `config-templates/Services/route-api/app/main.py`
- `config-templates/Configs/federation/aoa-routing.yaml`
- `mechanics/federation-seams/parts/sync-wrapper/README.md`
- `mechanics/federation-seams/parts/sync-wrapper/tests/test_routing_canary.py`
- `mechanics/federation-seams/parts/federation-checks/tests/test_route_api_closure_status.py`

## Follow-up route

Return to the runtime owner for isolated and operator-approved live canary
evidence. Return to `aoa-sdk`, `aoa-routing`, `abyss-machine`, and
`abyss-stack` together only when a distinct G5 producer-authority switch can be
reviewed without weakening this canary stop-line.
