# Admit External Actors Through Role-First Owner Contours

- Decision ID: ABYSS-STACK-D-0109
- Status: accepted
- Date: 2026-08-08
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/`

## Index Metadata

- Original date: 2026-08-08
- Surface classes: runtime boundary, actor admission, responsibility transfer, model-neutral invocation
- Stack lanes: source, runtime, review
- Mechanic parents: governed-execution
- Guard families: owner provenance, task-local DAG, exact binding, role-scoped MCP, observe-only usage
- Posture: accepted source-local owner contour; clean installed release and real-role proof remain open

## Context

D-0108 established that an exact Codex incarnation can live in a separate
process and durable session. Its first implementation was intentionally a
landing-oriented transport fixture. That shape could prove process mechanics,
but it could not prove the intended organ: a goal-generated obligation taking
on a persistent role, receiving responsibility and a domain procedure, and
returning through an explicit A2A relation.

Starting the public surface from a model or task family would also invert the
owner order. Luna is a current economical realization, not the reason an actor
exists. Landing, eval, stats, and memo are domain obligations, not runtime
concepts owned by `abyss-stack`.

## Options considered

- Expose a direct stable Luna launcher and let callers provide a prompt.
- Let the runtime infer obligations, roles, model fit, and domain procedures.
- Keep `owner_contour` schema-visible but admit only transport fixtures.
- Admit an external actor only after owner artifacts prove the obligation,
  mandate, task-local DAG, responsibility transfer, realization, binding, and
  domain procedure, while keeping physical launch binding neutral.

## Decision

Admit the external runtime through a role-first `owner_contour`.

`aoa-agents` owns detection of an independent obligation, role mandate,
responsibility transfer, and the semantic execution request. `aoa-skills` owns
the task-local DAG schema; the DAG remains a bounded projection of the goal,
not owner truth. Domain owners retain their actual procedures. `aoa-models`
owns current realization records and scoped fit claims. `aoa-sdk` binds the
selected incarnation's execution posture, tools, effects, continuation, wake
policy, and usage dimensions. `abyss-stack` owns only exact launch binding,
process/session lifecycle, tool-profile realization, observation, and return
receipts.

The stable physical leaf is `aoa-external-actor-bind`, not a model-named
launcher. It consumes already selected exact artifact paths, checks the owner
schemas pinned by runtime profile v2, hashes all launch coordinates, writes one
immutable launch, starts no process, and returns to `aoa-agents` to form the
separate `summon-request-v3`. The runtime admits both artifacts only when their
obligation, mandate, ready task-local DAG, accepted two-holder responsibility
transfer, domain procedure refs, child scope, separate process/session posture,
continuity, and observe-only usage semantics agree exactly.

Task families are open owner-qualified strings. Runtime behavior is selected
through model-neutral execution postures such as `bounded_execution`,
`independent_review`, `closeout`, and `ambiguity_stop`. Role-scoped read
profiles may configure exactly one named loopback AoA MCP; ambient and sibling
MCPs remain absent, the bearer token is excluded from the model shell, and the
task gains no general network or external-effect authority.

Usage is counted, not budgeted. Token, wall-time, turn, output, and command
observations support later stats/eval judgment but do not become runtime-
authored ceilings on a GPT-5.6 actor's initiative.

`transport_study_fixture` remains a compatibility and counterevidence lane.
It is not the production-shaped invocation route and cannot promote itself to
owner authority.

## Rationale

This order keeps the reason for an actor above its current computational body.
Roles and relationships can persist while a process stops or a realization
changes. Exact owner artifacts make responsibility movement reviewable without
asking the runtime to interpret domain meaning. The neutral binder gives every
fresh Codex session one repeatable physical invocation while preventing the
convenience command from becoming a hidden router or a Luna-specific API.

Real eval, stats, memo, and landing work can now supply useful role evidence
early. Deterministic tests remain focused on whether the actor contour actually
holds its contract, not on exhaustive sterile measurement before useful work.

## Consequences

- Positive: any supported model can incarnate a role without renaming the
  stable command or binding the role permanently to Luna.
- Positive: external CLI work is separately addressable and durable while
  built-in Codex subagents remain outside the proof.
- Positive: owner transfer, procedure, DAG, tools, effects, continuation, wake,
  and usage evidence are independently inspectable and exact.
- Positive: eval, stats, memo, and landing pilots can exercise actual owner
  procedures with guidance and independent review rather than broad fences.
- Tradeoff: callers must form several exact owner artifacts before launch;
  binder convenience deliberately does not erase those responsibilities.
- Tradeoff: role-scoped MCP availability depends on exact live service and
  credential admission, which source tests cannot prove.
- Follow-up: land the four owner sources, install a clean content-addressed
  release, run real Luna max/xhigh role pilots, prove fresh-session discovery,
  and route observed benefit/failures to stats and eval owners.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/runtime-profile.v1.json`
- `mechanics/governed-execution/parts/external-codex-agent/bind_external_actor_launch.py`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-actor-launch-manifest.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-launch.schema.json`
- `scripts/aoa-external-actor-bind`

## Follow-up route

`aoa-agents` and `aoa-summon` must publish the installed leaf invocation from a
complete actor DAG. Revisit this decision only if responsibility admission,
model realization selection, or A2A relationship ownership moves; changing a
model or domain procedure alone does not require a new runtime decision.
