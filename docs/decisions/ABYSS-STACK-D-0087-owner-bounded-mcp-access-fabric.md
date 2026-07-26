# Owner-Bounded MCP Access Fabric

- Decision ID: ABYSS-STACK-D-0087
- Status: accepted
- Date: 2026-07-25
- Owner surface: `mcp/`, MCP deployment, runtime lifecycle, and provenance

## Index Metadata

- Original date: 2026-07-25
- Surface classes: MCP runtime, lifecycle, provenance, policy plane
- Stack lanes: MCP access plane, runtime lifecycle, config projection
- Mechanic parents: runtime-lifecycle, config-projection
- Guard families: owner admission, effect isolation, provenance spine, rollback
- Posture: accepted target and transitional runtime law

## Context

The stack currently runs direct loopback MCP processes for multiple owners.
That lifecycle reduced duplicate client processes and added fail-closed bearer
authentication, but a 2026-07-25 baseline found one shared bearer and scope
across owners and across read, candidate, persistent-write, and
network-capable tools. It also found no deployed provenance manifest, no
process-reported source/package identity, large always-loaded catalogs, stale
or broken consumer registrations, and no independent stack MCP plane.

`ABYSS-STACK-D-0077` correctly established portable stdio, authenticated
loopback HTTP, source-owned units, and sequential lifecycle gates. Its shared
credential is not sufficient evidence for owner- or effect-level admission.
The stack needs a stronger runtime boundary without becoming a proxy for
sibling meaning.

## Options considered

- Keep the shared bearer and rely on MCP annotations and model cooperation.
- Put every owner tool behind one stack gateway and central policy check.
- Keep direct owner adapters, add a stack-owned runtime observation plane, and
  isolate policy families with separate processes, credentials, allowlists,
  receipts, and rollback.

## Decision

Choose the third option.

The stack owns the runtime half of the organ access fabric:

- package, export, deploy, process, listener, endpoint, consumer-registration,
  schema-observation, canary, and rollback observations;
- machine-readable deployment manifests and receipts linking reviewed source
  to the live process;
- protocol-independent identity, admission-input, request validation,
  authorization, approval, dispatch, result validation, receipt, and trace
  middleware;
- exact lifecycle execution only after an approved, bounded activation or
  runtime plan.

Sibling repositories retain capability and payload meaning. `aoa-sdk` owns
typed registry, discovery, and activation-plan compilation. `aoa-evals` owns
bounded proof interpretation. A memory or source owner accepts durable truth.
The stack may report those refs but cannot synthesize their verdict.

Every exported capability is classified by implementation as `observe`,
`derive`, `validate`, `prepare_candidate`, `apply_runtime`, `accept_source`,
`external_emit`, or `external_change`, then placed in one policy family:
`read`, `candidate`, `internal_effect`, or `external_effect`.

The runtime contour is process-level:

| Plane | Process and credential posture |
|---|---|
| read | owner-specific process exposing only non-persistent, non-network reads and bounded derives |
| candidate | separate owner-specific process and credential; writes only explicit candidate or temporary allowlisted paths |
| internal effect | separate process, credential, filesystem allowlist, approval, receipt, postcondition canary, and rollback |
| external effect | separate process and credential, disabled by default; exact external target, egress allowlist, expiring human approval, receipt, and rollback or compensating action |

The read credential cannot authenticate to or enumerate a higher-effect
process. Tool annotations mirror the classified posture but never enforce it.
If a capability spans policy families, it is split before admission.

`abyss-stack-mcp` becomes a first-class stack-owned organ plane, not a
gateway. Its read plane exposes source-package-deploy-process-endpoint-registry-
consumer evidence, schema observation, drift, canary, and rollback readiness.
Its candidate plane prepares immutable sync, deploy, activation, restart, and
rollback plans with exact targets and preconditions. Any runtime effect plane
is a later, separately admitted process. `abyss-stack-mcp` never proxies owner
tools, returns a flattened `healthy`, or treats process readiness as result
freshness.

For every admitted process, the stack produces a deployment manifest that
links:

```text
reviewed source commit
  -> package identity and digest
  -> deployed tree digest
  -> executable and process identity
  -> endpoint and protocol
  -> registry entry
  -> consumer-observed schema digest
  -> grounded canary
  -> owner acceptance ref
```

Each link has an observation timestamp and one of `exact`,
`compatible_drift`, `stale_readable`, `blocked`, `unknown`, or
`rollback_required`. `serverInfo.version` is package identity, not merely the
MCP SDK version.

Production remains on the confirmed stable MCP `2025-11-25` line until a
published final specification, exact stable SDK, and Codex pair pass official
and Abyss conformance. Registry, policy, provenance, and result contracts stay
protocol-independent. Stable and next adapters must coexist during a protocol
canary.

This decision narrows the admission interpretation of
`ABYSS-STACK-D-0077`; it does not remove its stdio, loopback, secret handling,
source-owned unit, parity, sequential restart, or canary requirements. The
current shared bearer is transitional authentication only. No effectful tool
is admitted under it.

Migration proceeds one owner and one plane at a time: source tests, package
parity, deploy preview, registry shadow, direct consumer canary, central proof,
owner acceptance, and rollback proof precede admission. Unready routes remain
shadow, suspended, or absent.

Rollback first denies discovery and activation, then restores the last-known-
good consumer registration, package, deployed tree, unit, credential class,
and process in reverse order. Old compatibility surfaces survive until
consumer-zero is proven. Authority rollback and protocol rollback are
independent.

## Rationale

Separate processes and credentials make the central security claim
testable: possession of a read credential cannot invoke an effect. Direct
owner adapters avoid a gateway that could become a confused deputy or merge
authority. A stack-owned observation plane provides the runtime evidence
agents need without moving domain meaning into the stack.

A protocol-independent middleware and provenance spine can be implemented now
while protocol drafts, SDK releases, and client support continue to move.

## Consequences

- Current active loopback services are shadow until owner, provenance, policy,
  proof, and acceptance gates are complete.
- Effect-spanning tools must be split or remain unadmitted.
- The stack must maintain more explicit processes, credentials, manifests, and
  receipts.
- Consumer projection must support per-plane endpoints and allowlists.
- A registry entry or process health can no longer stand in for grounded
  freshness.
- Runtime effects remain opt-in and human-approved; source and external effects
  require their own acceptance owners.

## Source surfaces

- `mcp/README.md`
- `mcp/services/README.md`
- `mcp/services/_shared/http_auth.py`
- `systemd/user/`
- `mechanics/runtime-lifecycle/`
- `mechanics/config-projection/`

## Follow-up route

Implement the shared policy and provenance contracts, then
`abyss-stack-mcp` read and candidate planes. Migrate compact read-only owners
first. Add effect processes only after focused threat models, negative
authorization tests, central evals, sequential canaries, and rollback proof.
