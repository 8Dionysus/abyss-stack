# Memo and Evals Candidate Contour Isolation

- Decision ID: ABYSS-STACK-D-0091
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mcp/services/aoa-memo-mcp/` and
  `mcp/services/aoa-evals-mcp/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP access plane, memory candidate, eval candidate
- Stack lanes: MCP services, organ access fabric, runtime lifecycle
- Mechanic parents: runtime-lifecycle
- Guard families: owner credential, effect isolation, filesystem write allowlist
- Posture: accepted source candidate-contour isolation

## Context

`aoa-memo-mcp` and `aoa-evals-mcp` each mixed broad read access with a narrow
persistent local-candidate surface in one process, endpoint, shared bearer,
scope, and client identity.

The writes are legitimate but weaker than their sibling owners:

- `aoa-memo` permits repo-local memory candidates, exports, forwarding
  receipts, and generated port indexes, while durable reviewed memory remains
  an `aoa-memo` source-owned reviewed-intake landing;
- `aoa-evals` decision `AOA-EV-D-0241` permits only sibling-local
  `evals/intake/*.eval_need.json`, `*.suite.md`, `*.report.md`, and the paired
  `PORT.yaml` skeleton-to-active transition, while proof acceptance and central
  bundles remain owner source work.

A bearer that can read an organ must not silently inherit its candidate write
authority. Runtime inventory discovery must also not expand the writable
filesystem by itself.

## Options considered

1. Keep both mixed endpoints and rely on `apply=false`, schema validation, and
   tool descriptions.
2. Remove MCP persistence and require all local candidates to be written
   outside MCP.
3. Split read and candidate into separate authenticated processes, preserve the
   owner-approved local candidate routes, and enforce each write through both
   application and OS allowlists.

## Decision

Choose option 3.

Memo read remains on port `5421`; Memo candidate uses port `5434`. Evals read
remains on port `5424`; Evals candidate uses port `5435`. Each contour has a
distinct bearer environment variable, systemd credential, authorization
scope, client identity, server identity, and observed tool catalog.

Read catalogs contain no persistent tools and run through
`aoa-organ-mcp-read@.service` with no writable filesystem path. Candidate
catalogs expose only the owner-approved local writers and no resources.

Candidate core calls require `AOA_MCP_POLICY_FAMILY=candidate` and an exact
target match under the corresponding configured candidate-root list. Dedicated
systemd units independently grant only the enumerated local packet/index paths
for Memo and local intake/suite/report/PORT paths for Evals. Durable Memo
objects, central Evals bundles, Evals suite execution sidecars, receipts,
verdicts, scoring, promotion, execution, and arbitrary sibling paths remain
unwritable.

Adding a future writable local port requires an explicit source change to both
the application root list and the systemd path list. Read discovery alone is
not write admission.

## Rationale

Process, credential, catalog, application, and filesystem boundaries now agree
on effect class. This makes read-to-candidate denial observable and limits a
candidate-server compromise to reviewed local pressure lanes instead of the
whole workspace.

Keeping the owner-approved local candidate route preserves useful agent
authoring without turning MCP into durable memory or proof authority. Explicit
source-enumerated growth is slower than automatic write discovery, but it is
reviewable, testable, and rollbackable.

## Consequences

- Existing `aoa_memo` and `aoa_evals` read registrations must move to the new
  owner-read bearer variables before canary.
- Candidate consumers require separate registration names and endpoints; a
  read registration cannot invoke a writer.
- The credential provisioner manages eight owner-read and two Memo/Evals
  candidate values and rejects equality across the complete set.
- The default owner bundle now names the two read instances and two candidate
  services instead of the prior mixed Memo/Evals instances.
- The deployed `abyss-stack/Configs/memo` port is currently absent, so the
  managed Memo candidate contour cannot write an abyss-stack local candidate
  until an owner-approved deployed-port route exists.
- These are unlanded source candidates. They do not prove packaging,
  deployment, process health, endpoint readiness, consumer compatibility,
  denial behavior, grounded results, owner acceptance, benefit, or rollback.

## Relationship to prior decisions

- Applies the owner/effect separation law from `ABYSS-STACK-D-0087`.
- Extends the behavior-first isolation sequence from
  `ABYSS-STACK-D-0088` through `ABYSS-STACK-D-0090`.
- Preserves `aoa-memo` decision `AOA-MEM-D-0064`: durable reviewed intake is
  owner source work, not MCP acceptance.
- Preserves `aoa-evals` decision `AOA-EV-D-0241`: only the narrow sibling-local
  write allowlist is exposed.

## Source surfaces

- `mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/core.py`
- `mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/server.py`
- `mcp/services/aoa-evals-mcp/src/aoa_evals_mcp/core.py`
- `mcp/services/aoa-evals-mcp/src/aoa_evals_mcp/server.py`
- `systemd/user/aoa-organ-mcp-read@.service`
- `systemd/user/aoa-memo-mcp-candidate.service`
- `systemd/user/aoa-evals-mcp-candidate.service`
- `systemd/user/aoa-mcp-http.service`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `mcp/services/_shared/codex_http_client.sh`

## Follow-up route

Keep both organs shadow in O1. During the final integrated landing, package and
deploy the exact source, register read/candidate consumers separately, inspect
both tool catalogs, prove cross-contour authentication denial and filesystem
confinement with non-destructive canaries, obtain owner acceptance, and prove
rollback before changing any registry maturity axis.
