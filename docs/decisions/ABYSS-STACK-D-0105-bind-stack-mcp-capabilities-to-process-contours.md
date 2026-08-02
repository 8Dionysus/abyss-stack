# Bind Stack MCP Capabilities to Process Contours

- Decision ID: ABYSS-STACK-D-0105
- Status: accepted
- Date: 2026-08-01
- Owner surface: `mcp/services/abyss-stack-mcp/organ-access.v1.json`

## Index Metadata

- Original date: 2026-08-01
- Surface classes: MCP access plane, capability identity, owner contract
- Stack lanes: MCP services, organ access fabric, consumer admission
- Mechanic parents: runtime-lifecycle
- Guard families: exact tool binding, credential isolation, fail closed, no implied admission
- Posture: accepted owner capability identity

## Context

The stack MCP already exposes three bounded read tools and one non-executing
candidate tool through separate processes. Its source described the process
contours, but did not provide one machine-readable owner contract that bound
their durable capability IDs, primitive IDs, tool names, schemas, credential
classes, and authority limits.

Without that source, a registry or consumer projection could invent a
capability at integration time, retain an obsolete primitive name, or confuse
the systemd credential filename with the owner credential class. Runtime
presence, a successful call, and a consumer registration would then be unable
to prove that they referred to the same owner-authored capability.

## Options considered

- Derive capability identity from discovered MCP tool names at runtime.
- Treat the private registry or consumer projection as the capability owner.
- Publish one strict package-local owner manifest and require downstream
  admission evidence to preserve its exact identities.

## Decision

Choose the package-local owner manifest.

`runtime-topology-read` is the read capability. It binds
`runtime-catalog`, `runtime-inspect`, and
`cross-organ-orchestration-inspect` to the three existing read tools and uses
credential class `abyss-stack-read`.

`stack-access-plan` is the candidate capability. It binds
`prepare-runtime-plan` to `stack_prepare_runtime_plan` and uses credential
class `abyss-stack-candidate`.

The two contours must remain distinct. The strict model rejects a changed
capability, primitive, tool, credential, effect class, idempotency posture, or
missing candidate rollback route. The authored manifest sets admission,
registry mutation, and effect activation authority to false. A generated JSON
Schema and package tests keep the data contract synchronized with the running
policy seams.

## Rationale

Capability identity is owner truth; transport discovery is only an
observation of one server instance. Keeping the manifest beside the server
source gives registries, consumers, admission transactions, proof packets, and
runtime observations one exact anchor without allowing any of them to acquire
owner authority.

Separating credential class from the deployment-specific environment variable
and systemd credential filename also preserves the boundary between a durable
policy identity and its current secret-delivery mechanism.

## Consequences

- Positive: downstream surfaces can reject identity drift before registry or
  consumer mutation.
- Positive: the read and candidate processes retain exact, independently
  credentialed capability contours.
- Tradeoff: any deliberate primitive or tool rename now requires an owner
  contract revision and downstream admission refresh.
- Claim limit: this decision proves source identity and source/runtime tool
  correspondence only. It does not prove package/deploy parity, live
  admission, owner acceptance, consumer freshness, benefit, or effect safety.

## Source surfaces

- `mcp/services/abyss-stack-mcp/organ-access.v1.json`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/organ_access.py`
- `mcp/services/abyss-stack-mcp/schemas/organ-access.schema.json`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/server.py`
- `mcp/services/abyss-stack-mcp/tests/test_organ_access.py`
- `mcp/services/abyss-stack-mcp/README.md`

## Follow-up route

Use the exact owner manifest as the first source anchor of the organ-admission
transaction. Refresh package, deploy, process, endpoint, consumer, canary,
owner-grounding, proof, acceptance, and rollback evidence independently; no
later stage may infer admission from this decision.
