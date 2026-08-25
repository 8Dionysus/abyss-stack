# Canonical Codex 0.149.1 Runtime Subject Admission

- Decision ID: ABYSS-STACK-D-0137
- Status: accepted
- Date: 2026-08-25
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent`
- Supersedes: `ABYSS-STACK-D-0128`

## Index Metadata

- Original date: 2026-08-25
- Surface classes: public-contract, runtime-profile, source/runtime boundary
- Stack lanes: governed-execution, external Codex runtime, model admission
- Mechanic parents: `mechanics/governed-execution/parts/external-codex-agent`
- Guard families: model admission, runtime identity, source/runtime separation
- Posture: accepted migration rationale

## Context

`ABYSS-STACK-D-0128` recorded the exact-subject admission shape while the
external Codex lane was pinned to 0.148.0. The current owner profile and
admitted shared runtime have moved to Codex 0.149.1, so the older decision's
version statement and package rationale no longer describe the active source
contract. Leaving that statement active would direct an operator toward a
package that the current exact-admission checks reject.

## Options considered

- Keep the 0.148.0 wording and treat the current profile as undocumented drift.
- Change the old decision in place and lose the historical rationale for the
  0.148.0 admission boundary.
- Record a superseding 0.149.1 decision while preserving the older record as
  immutable history, with the source profile remaining authoritative for exact
  subjects.

## Decision

The canonical external Codex lane admits Codex CLI 0.149.1 together with the
exact content-addressed runtime subject, package inventory, transport, access
regime, and lifecycle constraints declared by the owner
`runtime-profile.v1.json`. The owner contract names the same 0.149.1 pin.
`ABYSS-STACK-D-0128` remains the historical rationale for the earlier 0.148.0
boundary and is superseded for current admission; it is not edited into a
second active contract. Exact subject values continue to come from the
profile and the model-admission catalog rather than from this rationale note.

This decision records source authority only. It does not by itself claim that
an arbitrary host is activated, that a runtime package is admitted, or that a
semantic canary or owner acceptance has occurred.

## Rationale

Keeping one current profile/contract pair and a superseding rationale preserves
the fail-closed byte-for-byte subject check while retaining an auditable reason
for the migration. The stack continues to own the runtime profile and launch
boundary, while `aoa-models` owns realization meaning and `abyss-machine` owns
artifact admission and activation evidence.

## Consequences

- Positive: current readers find an explicit 0.149.1 admission rationale and
  cannot mistake the historical 0.148.0 record for the active pin.
- Positive: exact subject equality, package inventory checks, and source/runtime
  separation remain unchanged.
- Tradeoff: the source profile, model realization, admitted artifact, and live
  canary still require separate current evidence; this record is not a runtime
  receipt.
- Follow-up: use the owner release and runtime routes to prove admission,
  activation, rebind/resume, semantic canary behavior, and canonical return.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/runtime-profile.v1.json`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/bind_external_actor_launch.py`
- `aoa-models` runtime-admission catalog and realization source
- `ABYSS-STACK-D-0128` historical exact-subject rationale

## Follow-up route

The owner release/runtime route must keep the profile, admitted package,
installed shared runtime, and fresh 0.149.1 semantic canary aligned. Revisit
this decision only when the canonical runtime pin or its exact subject changes.
