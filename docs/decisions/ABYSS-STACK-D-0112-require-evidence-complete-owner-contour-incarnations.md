# Require Evidence-Complete Owner-Contour Incarnations

- Decision ID: ABYSS-STACK-D-0112
- Status: accepted
- Date: 2026-08-10
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-10
- Surface classes: runtime boundary, actor admission, incarnation evidence, content identity
- Stack lanes: source, runtime, review
- Mechanic parents: governed-execution
- Guard families: owner provenance, exact binding, model-fit evidence, responsibility transfer, semantic digest
- Posture: accepted source-local admission ABI; clean owner landing and live role proof remain open

## Context

D-0110 admitted role-first external actors through an `aoa-agents`
`summon-request-v3` and the first SDK incarnation binding. That contour proved
that obligation, mandate, task-local DAG, responsibility transfer, domain
procedure, process, session, continuation, and usage posture could agree at
launch. It did not bind the exact role-resolution object or the exact
`aoa-models` query and projection that justified the selected realization.

The owner contracts now expose those missing links through `aoa-summon`
request v4 and `AgentIncarnationBindingV2`. New owner-contour execution must
consume that evidence without making `abyss-stack` a role selector, model-fit
authority, or activation router. The new owner objects also distinguish a
canonical semantic self-digest from the raw SHA-256 used to transport one
immutable JSON file; treating those digests as interchangeable rejects valid
owner objects or weakens byte identity.

## Options considered

- Continue accepting summon v3 and SDK binding v1, and infer the absent role
  and fit chain from the delivered model realization.
- Let `abyss-stack` query roles and models during launch and construct the
  missing evidence itself.
- Require summon v4 plus SDK binding v2 for every new owner-contour launch,
  preserve v1 only for historical transport receipts, and verify semantic and
  transport digests as distinct identities.

## Decision

Every new `owner_contour` execution requires the exact runtime-profile-pinned
`aoa-agents` `summon-request-v4` and an
`aoa_agent_incarnation_binding_v2`. The request and binding must name the same
agent obligation, actor mandate, exact role resolution, model-fit query
result, selected model-fit projection, SDK summon request and decision,
runtime launch, task-local DAG, responsibility transfer, domain procedures,
continuity, and return-event schema.

The runtime validates that the mandate preserves the obligation holder,
return owner, stop line, role binding, environment, effects, tools, MCP
profile, and named outputs. It also verifies one exact informational
`aoa-models` candidate chain from the mandate's explicitly authorized
task-family relation through query result and projection to the already bound
model realization. This verification does not choose a role or model and does
not grant `aoa-models` routing, activation, proof, or acceptance authority.

Immutable input transport continues to require raw byte SHA-256 through its
`ProvenanceRef`. `agent-obligation-v1`, `actor-mandate-v1`,
`aoa_role_resolution_v1`, and `aoa_model_fit_query_result_v2` `ContentRef`
identities additionally require their owner-defined canonical self-digests.
The runtime checks both classes rather than equating them.

The SDK request remains in SDK vocabulary: its external transport is
`a2a_remote` or `either`. The `aoa-summon` leaf translates only that field to
`external_cli` and removes the SDK's duplicate nested output list; passport,
task identity, capability, review, workspace, and top-level named outputs must
otherwise remain exact. The final owner request also verifies its canonical
digest with `request_digest` omitted, as defined by `aoa-summon`.

SDK binding v1 remains readable for existing `transport_study_fixture`
receipts, resume, review, and historical evidence. It is not sufficient for a
new owner-contour responsibility transfer. Built-in Codex subagents remain
outside this external-incarnation proof, and usage remains observe-only
counting without an execution budget.

This decision supersedes only the summon-v3 and binding-v1 admission ABI
described by D-0110. D-0110's owner split and D-0111's external process,
session, projection, continuation, and return boundaries remain accepted.

## Rationale

The actor's meaning must be established before runtime activation, and its
current computational body must remain replaceable. Requiring exact role and
fit evidence closes the last model-first inference seam while leaving each
decision with its proper owner. Separating semantic identity from transport
identity preserves both owner-defined content addressing and immutable byte
delivery instead of weakening one to satisfy the other.

Keeping v1 readable but non-admissible for new owner execution preserves the
large body of transport and continuation evidence without allowing historical
fixtures to masquerade as evidence-complete responsibility transfer.

## Consequences

- Positive: every admitted owner-contour process has an inspectable chain from
  obligation and role through current fit evidence to the exact realization.
- Positive: changing Luna, effort, or a later model does not mutate the stable
  role or public invocation semantics.
- Positive: old transport receipts remain usable for their original evidence
  class while new responsibility transfers fail closed on v1.
- Tradeoff: callers must provide two additional owner objects and preserve
  both their semantic digests and raw transport provenance.
- Tradeoff: the current landing study preparer remains a transport-study
  compiler until a general role-first owner compiler emits the complete v4
  packet without hand-authored JSON.
- Follow-up: build that owner-separated compiler, run the first real landing
  owner-contour pilot, and then apply the same route to eval, stats, and memo
  obligations.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/runtime-profile.v1.json`
- `mechanics/governed-execution/parts/external-codex-agent/install_external_codex_runtime.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`

## Follow-up route

`aoa-agents` remains responsible for obligation, mandate, role, and transfer;
`aoa-models` for fit evidence; `aoa-sdk` for the incarnation binding; and
`abyss-stack` for physical runtime admission and lifecycle. Revisit this
decision if those owner boundaries or the meaning of semantic content identity
change, not merely when a model realization or domain procedure changes.
