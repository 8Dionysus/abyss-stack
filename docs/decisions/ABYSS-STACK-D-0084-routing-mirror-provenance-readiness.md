# Routing Mirror Provenance Readiness

- Decision ID: ABYSS-STACK-D-0084
- Status: accepted
- Date: 2026-07-24
- Owner surface: `mechanics/federation-seams/`

## Index Metadata

- Original date: 2026-07-24
- Surface classes: runtime route contract, health contract, validation topology
- Stack lanes: source checkout, runtime mirror, release/tooling
- Mechanic parents: federation-seams
- Guard families: federation sync, route-api closure status, artifact provenance
- Posture: accepted fail-closed consumer contract

## Context

The routing mirror was false-green in two independent ways.

First, `route-api` tested retired `version` fields even though the current
`aoa_routing_thin_router_v1` artifacts use `registry_version`,
`router_version`, and schema-qualified `schema_version` fields. It therefore
accepted a stale v1 mirror while rejecting the current canonical bytes.

Second, sync checks compared file presence and source commit but did not
re-hash mirrored content. Health reported every layer ready without exposing
the routing artifact identity, mirror source ref, content-hash posture, or
absence of a trust verdict.

This became a hard blocker for the `aoa-sdk` routing-producer succession G4
runtime-mirror dry run. Hiding the difference in SDK-side evidence would have
left the runtime owner unable to distinguish current routing bytes from a
stale or tampered mirror.

## Options considered

- Treat a successful file copy as sufficient G4 evidence and leave
  `route-api` health unchanged.
- Patch the candidate routing artifacts to restore the retired `version`
  fields expected by the runtime.
- Make the runtime consumer understand the stable current ABI, verify mirror
  hashes, and report content, consumer, provenance, and trust readiness
  separately.

## Decision

Keep the routing artifact bytes and ABI unchanged. Update the runtime consumer.

`route-api` accepts the stable routing version fields according to each
surface: `router_version`, `registry_version`, `schema_version`, or the legacy
`version` compatibility field. It loads the federation mirror manifest,
verifies the exact required-file list and hashes, and exposes routing artifact
identity, source ref, hash posture, and trust-verdict availability.

Trust admission is not a free-form boolean. A present verdict must be an
`abyss_machine_artifact_trust_gate_v1` runtime-consumer result that selects the
latest durable record and binds its source ref and subject digest to the
manifest and routing artifact identity.

Health exposes only an allowlisted trust summary. The runtime may inspect the
durable record to validate bindings, but it must not return the full record or
deploy-local evidence references through a service endpoint.

Routing closure now requires four independently visible conditions:

1. required mirror files are present;
2. current routing payloads are consumable;
3. source and content provenance are valid;
4. a trust verdict admits the exact routing read model.

The sync wrapper re-hashes every required mirrored file before returning
`status:"ok"`. A missing source ref or trust verdict remains explicit
provenance debt. An isolated succession rehearsal may prove content and
consumer readiness with stronger outer evidence, but it cannot claim live
closure or authorize publication.

## Rationale

The runtime owns consumption, health, and mirror hygiene. It should adapt to a
stable owner ABI rather than ask a successor producer to emit obsolete fields.

Separating content readiness from provenance and trust keeps a useful G4 dry
run possible without turning an ephemeral candidate assembly into live
authority. The same split makes deployed health fail closed when bytes are
stale, tampered, source-unbound, or not trust-admitted.

This change does not transfer routing meaning into `abyss-stack`. It only makes
the runtime's read boundary honest enough to consume the current owner surface
and the future SDK-produced compatibility surface.

## Consequences

- Positive: current `aoa_routing_thin_router_v1` bytes load without an ABI
  rewrite.
- Positive: sync detects mirrored-byte tampering even when source commit and
  file presence appear current.
- Positive: `/health` and `/surface-status` no longer return an unconditional
  green state when routing provenance or trust is absent.
- Positive: a forged bare `allow` field cannot satisfy runtime closure without
  exact source, subject, and durable-record bindings.
- Positive: route-api does not leak the complete durable registry record while
  reporting trust readiness.
- Tradeoff: existing deployed mirrors remain degraded until they are refreshed
  and supplied with an exact trust verdict through an operator-approved
  runtime route.
- Tradeoff: the current federation manifest has no trust-verdict producer;
  owner succession must design that intake before G5 live cutover.
- Follow-up: `aoa-sdk` G4 may use this source contract only in an isolated
  mirror. Live deployment, SDK producer identity in the manifest, and service
  restart remain separate M2/G5 operator-owned actions.

## Source surfaces

- `config-templates/Services/route-api/app/main.py`
- `config-templates/Configs/federation/aoa-routing.yaml`
- `mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh`
- `mechanics/federation-seams/parts/sync-wrapper/tests/test_sync_wrapper_freshness.py`
- `mechanics/federation-seams/parts/federation-checks/tests/test_route_api_closure_status.py`
- `mechanics/federation-seams/parts/sync-wrapper/README.md`

## Follow-up route

Return to `aoa-sdk` for the G4 released-shadow, package-trust, rollback, and
isolated runtime-mirror evidence. Return here during M2/G5 only for the
runtime-owned producer-identity, trust-verdict intake, deployment, health, and
rollback contract.
