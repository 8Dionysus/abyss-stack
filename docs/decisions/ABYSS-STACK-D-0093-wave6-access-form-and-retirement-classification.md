# Wave 6 Access-Form and Retirement Classification

- Decision ID: ABYSS-STACK-D-0093
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mcp/` and OS Abyss organ-access portfolio

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP access plane, organ portfolio, compatibility retirement
- Stack lanes: MCP services, organ access fabric, runtime lifecycle
- Mechanic parents: runtime-lifecycle
- Guard families: owner boundary, narrowest access form, consumer-zero, rollback
- Posture: accepted runtime access-form classification

## Context

The first five O1 waves produced fifteen deny-by-default shadow records for
organs whose current owner contracts justify a service-backed MCP contour.
Wave 6 covers the remaining owner surfaces. Center law explicitly says that a
repository is not required to expose MCP and that an SDK API, CLI, resource
projection, skill, KAG/stats projection, or no separate plane can be the
correct access form.

The Wave 6 review used remote-verified owner `main` revisions:

| Owner | Reviewed revision | Owner evidence |
|---|---|---|
| `8Dionysus` | `419b35990c41b995bcf3d8be210f244f97fcdddf` | `AGENTS.md`, `README.md` |
| `ATM10-Agent` | `1f3c1753776936fd50206045754f0895c6aa1d93` | `AGENTS.md`, `README.md` |
| `Agents-of-Abyss` | `81f6ef479b14ff29684e1fa40aa499c6c6bd9b39` | organ contract and D-0032 |
| `Dionysus` | `8c5c8ec960c507e097b37472e9e8353c369919bf` | `AGENTS.md`, `README.md`, `DESIGN.md` |
| `aoa-agents` | `8e5a989428a11108b8fc427cb351c313df2a14c2` | `AGENTS.md`, `README.md`, `DESIGN.md` |
| `aoa-playbooks` | `577b772c62b692b18a7f0945a470d00245c998c8` | `AGENTS.md`, `README.md`, `DESIGN.md` |
| `aoa-routing` | `97f60de1b5992ef6bf5ff0f051bd452d940d9a85` | `AGENTS.md`, `README.md` |
| `aoa-sdk` | `5de159e449cc8d5ae93475db6b56a7b7279bc67b` | D-0075, D-0076, organ-access and workspace-MCP contracts |
| `aoa-skills` | `9b009123e88cd864ef11147a6d9cba31a3bf81a5` | `AGENTS.md`, `README.md`, `DESIGN.md` |
| `aoa-techniques` | `e842c0d0156c58cfb9020b636e81134e96fc8cfb` | `AGENTS.md`, `README.md`, `DESIGN.md` |

The SDK owner has now accepted D-0076: its G5 receipt authorizes `aoa-sdk` as
the canonical routing producer and starts the compatibility window. The
current `aoa-routing` owner revision still describes the pre-G5/M2 state and
has not landed the paired M3 maintenance receipt. This is a real transitional
split, not authority to archive the predecessor.

The current `Dionysus` owner is also no longer the seed-garden surface named by
the stale workspace MCP hints. It is a privacy-sensitive portrait-protocol
skeleton that explicitly defers agent and MCP integration.

In a separate, still-unlanded SDK worktree, D-0079 now projects the existing
typed progressive-discovery API through four read-only `aoa_workspace` MCP
tools and four resources. It intentionally exposes no activation-plan,
registry-write, connection, lifecycle, or execution tool. That source
candidate refines the access form but does not alter the remote-main revision
reviewed above or establish package/runtime admission.

## Options considered

1. Add one service-backed MCP server for every remaining repository.
2. Put all remaining repositories behind the stack MCP as a semantic gateway.
3. Select the narrowest owner-supported access form, add no registry record
   when MCP is unjustified, and keep stale predecessors as explicit retirement
   candidates until consumer-zero and rollback gates pass.

## Decision

Choose option 3.

| Owner | Current outcome | Selected access form |
|---|---|---|
| `8Dionysus` | MCP not needed | public resources and source-owned workspace projection |
| `ATM10-Agent` | MCP not needed | owner package and CLI |
| `Agents-of-Abyss` | MCP not needed | constitutional source plus generated resource/KAG projections |
| `aoa-agents` | MCP not needed | owner role sources, generated Codex projections, and SDK readers |
| `aoa-playbooks` | MCP not needed now | owner playbook projections plus explicit host/SDK orchestration |
| `aoa-skills` | MCP not needed | host skill activation plus capability/KAG projection |
| `aoa-techniques` | MCP not needed | authored resources plus compact/KAG projections |
| `Dionysus` | legacy/retirement candidate | current owner protocol/resources; stale MCP removal only after consumer-zero |
| `aoa-routing` | legacy/retirement candidate | SDK canonical producer; predecessor retained for compatibility and rollback |
| `aoa-sdk` | package candidate | typed registry/discovery/candidate-plan API and workspace MCP control plane |

Wave 6 contributes no organ registry record. This is deliberate exclusion
after owner review, not missing inventory coverage. The O1 shadow registry
therefore remains fifteen records, all `shadow`, with no endpoint and only the
`declared` maturity axis asserted.

`aoa-sdk` is different from the seven no-MCP owners: its typed control plane
and existing workspace MCP are relevant package candidates. It remains
unadmitted until the discovery source candidate is landed and packaged and the
OS-private registry instance, exact deploy identity, observed consumer schema,
canary, central proof, owner acceptance, and rollback are demonstrated.

## Rationale

A universal one-repository/one-server rule would add catalog weight and
lifecycle risk while obscuring the actual owner forms. Static law, role
sources, skills, technique resources, a local product CLI, and scenario
projections do not become better owners merely because MCP can wrap them.

Retirement also needs evidence. Removing `Dionysus` configuration before
consumer-zero could break an unknown consumer, while removing `aoa-routing`
before its paired M3 and compatibility exit would destroy the exact rollback
source required by the accepted succession.

The SDK control plane remains a candidate because typed discovery is useful to
agents, but it must not infer runtime activation, proof, or owner acceptance
from its own registry projection.

## Consequences

- No new MCP package, credential, process, port, or registry entry is created
  for the seven no-MCP owners.
- The stale Dionysus workspace hints must be corrected in source before the
  final consumer projection is rendered.
- `aoa-routing` receives no new features or MCP surface; compatibility,
  security, rollback, deprecation, M3, and consumer-zero remain its only valid
  transition work.
- The `aoa-sdk` source candidate exposes progressive organ discovery through
  the workspace MCP read plane, but candidate compilation stays an explicit
  SDK or host operation and runtime execution stays outside the SDK.
- A future owner may reopen an access-form decision with a new contract and
  evidence. This decision does not permanently forbid MCP where the owner
  later demonstrates distinct value.

## Claim limits

This decision proves a source-bounded access-form review at the cited remote
revisions. It does not prove owner acceptance of an MCP adapter, package or
deploy parity, live process health, endpoint readiness, consumer registration,
consumer-zero, archive readiness, runtime cutover, grounded calls, benefit, or
rollback.

## Source surfaces

- `mcp/`
- `docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md`
- the cited remote owner contracts
- the O1 portfolio under
  `/srv/abyss-machine/tmp/ai/os-abyss-mcp-o1-organ-waves-20260726`

## Follow-up route

Correct the SDK workspace read plane and source-owned Codex projection,
validate the complete O1 portfolio, then proceed to the explicit
KAG-to-memo-to-eval-to-acceptance orchestration proof. Do not remove either
legacy route or change live consumer configuration before the final integrated
landing gates.
