# Fail Closed MCP Admission Maintenance

- Decision ID: ABYSS-STACK-D-0107
- Status: accepted
- Date: 2026-08-08
- Owner surface: `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/admission_automation.py`

## Index Metadata

- Original date: 2026-08-08
- Surface classes: MCP access plane, runtime admission, operational evidence
- Stack lanes: MCP services, runtime lifecycle, organ access fabric
- Mechanic parents: runtime-lifecycle
- Guard families: fail closed, contour isolation, exact identity, immutable evidence, periodic backstop
- Posture: accepted bounded admission maintenance

## Context

Managed MCP processes could remain live after registry evidence expired, and
their start units did not prove that source, deployed package, executable,
credential, schema, and contour still described the same instance. Replaying a
full admission manually for every TTL or small change is both expensive and
likely to hide partial drift.

## Options considered

- Treat active systemd state and successful calls as sufficient health.
- Let the stack refresh owner acceptance, proof, or registry timestamps.
- Add exact per-contour preflight plus an event-driven, timer-backed consumer of
  the SDK Admission Keeper while preserving every stronger owner gate.

## Decision

Choose the third option.

Each read contour present in the committed runtime-target catalog and backed
by a successful, current, content-addressed canary attested by the pinned stack
public key receives a fail-closed `ExecCondition` bound to a private catalog.
Candidate and internal-effect units remain outside this gate until their own
target and evidence contracts exist; the read-only canary cannot be promoted
into evidence for them. Preflight checks registry expiry/state, policy and authority,
allowlist, endpoint and protocol, source/package/deployment identities,
deployed tree, pinned executable realpath and digest, regular non-symlink
credential value, auth manifest, schemas, validator, unit environment, and
dependency lock. Failure emits exact expected/observed identities and never
authorizes a restart loop.

The stack derives a non-admitting runtime overlay from deployment and canary
receipts, derives private topology and catalog, runs a bounded preflight sweep,
builds Keeper specs, and asks the SDK to CAS-publish contour states. File/path
events are primary; a five-minute timer is only a backstop. The automation does
not start services, mutate registry source, extend evidence, issue proof, or
infer acceptance.

## Rationale

Runtime identity belongs to the stack, but organ source, proof, acceptance, and
registry authority do not. Separating observation and planning from issuance
lets cheap stages refresh automatically while stale or missing stronger-owner
nodes remain visible blockers. It also makes a live-but-expired service
explicit instead of green.

## Consequences

- A standard venv executable symlink is accepted only when its resolved target
  and digest match; credentials remain regular non-symlink mode `0600` files.
- Template systemd credentials are checked as exact unit lines rather than
  mistaken for literal instance paths.
- Missing canary or registry contours are reported individually and do not
  fabricate topology.
- Candidate and internal-effect services are not permanently blocked on read-only
  bindings that admission automation cannot build.
- The current private registry remains fail-closed when expired even if every
  process is active and all lower runtime identities match.
- The Keeper runtime requires an exact compatible `aoa-sdk` artifact before
  deployment; source presence alone is not that artifact proof.

## Source surfaces

- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/preflight.py`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/admission_automation.py`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/managed_catalog.py`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/managed_topology.py`
- `mcp/services/abyss-stack-mcp/src/abyss_stack_mcp/runtime_overlay.py`
- `systemd/user/abyss-mcp-admission-keeper.*`
- `systemd/user/aoa-organ-mcp-read@.service`
- `systemd/user/abyss-stack-mcp-*.service`

## Follow-up route

Package and attest the exact SDK dependency, refresh owner-issued evidence
through independent gates, then deploy the units and prove source/deployed
parity. Protocol migration and MCP Tasks remain separate admissions and must
not inherit this runtime result.
