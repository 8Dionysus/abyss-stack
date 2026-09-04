# Prompt-Light Agent Routes And On-Demand Validation

- Decision ID: ABYSS-STACK-D-0140
- Status: accepted
- Date: 2026-08-31
- Owner surface: `AGENTS.md`, `DESIGN.AGENTS.md`, `VALIDATION.md`, and `docs/validation/validation_lanes.json`

## Index Metadata

- Original date: 2026-08-31
- Surface classes: agent guidance, docs route, validation guard, public contract
- Stack lanes: source, docs and routes, validation, release/tooling
- Mechanic parents: none
- Guard families: nested AGENTS, inherited context, route locality, validation lane
- Posture: accepted source-route rationale; no runtime admission, deployment, or exposure change

## Context

`ABYSS-STACK-D-0018` kept the public README concise by moving exact validation
commands into root and local `AGENTS.md` cards. `ABYSS-STACK-D-0139` later
removed repeated MCP command matrices from parent cards and added a 32-KiB
inherited-chain guard, while retaining exact package commands in the nearest
`AGENTS.md`.

Those choices improved the human front door and bounded the largest inherited
chains, but they still make executable procedure part of automatically loaded
agent context. The current corpus has 59 tracked `AGENTS.md` cards, 56 with
fenced command blocks. It also has cards that require README inventories before
the actual touched surface is known. A local route can therefore inherit
unrelated procedure and turn human explanation into prompt-mandatory context
even when the repository already has stronger validation topology:

- `docs/validation/validation_lanes.json` owns executable lane sequences;
- `scripts/validation_lanes.py` validates and loads them;
- `scripts/ci_gate.py` executes named lanes;
- package-local validators and focused tests own their exact contracts.

The durable question is not whether validation remains discoverable. It is
which document role can preserve validation without repeatedly injecting its
procedure into inherited agent context.

## Options considered

- Keep exact commands in the nearest `AGENTS.md` and rely only on the existing
  32-KiB chain budget.
- Move exact commands into README files so the agent cards become smaller.
- Keep `AGENTS.md` as a prompt-light inherited semantic delta, expose exact
  human-executable procedure through on-demand `VALIDATION.md`, and retain the
  lane manifest as machine command authority.

## Decision

Choose the third option.

Root and nested `AGENTS.md` remain inherited route cards. A card may own the
applicable scope, local role, conditional source routes, owner and authority
boundaries, risk and approval stop-lines, a validation-route link or lane ID,
and closeout requirements. It must not duplicate runnable command sequences,
full release or GitHub landing procedure, or an unconditional inventory of
README files merely because the agent entered a subtree.

Exact human-executable validation procedure moves to the nearest unambiguous
`VALIDATION.md`. Root `VALIDATION.md` is the on-demand map for repository-wide
lanes. `docs/validation/validation_lanes.json` remains the machine authority
for named lane sequences, and the existing loaders and runners continue to
enforce and execute it. A package-local `VALIDATION.md` may add exact focused
commands only for the package that owns them; it must not fork a stronger
manifest-owned sequence.

README remains the human and public semantic navigation surface. A README may
explain purpose, usage, examples, package topology, and public entry routes.
An `AGENTS.md` may point to a README when the current task actually needs that
semantic contract, but entering a directory does not make every inherited or
local README mandatory reading. Root `README.md` remains the public repository
front door. This decision does not authorize blanket README deletion, rename,
or consolidation; each non-root disposition requires separate link, semantic,
generator, fixture, and public-consumer evidence.

The ordinary branch, pull-request, CI, merge, and release procedure belongs in
`docs/governance/RELEASING.md`. Root `AGENTS.md` keeps only the route, required
evidence class, and stop-line for unobservable CI or merge authority.

This decision supersedes only the validation-command placement in
`ABYSS-STACK-D-0018` and the nearest-card exact-command placement in
`ABYSS-STACK-D-0139`. It preserves the entry-route contract, public README
boundary, 32-KiB inherited-chain guard, route locality, package-owned checks,
and all source/runtime, proof, security, approval, deployment, and merge
boundaries established by those records.

## Rationale

Automatically inherited context should carry the small set of constraints an
agent cannot safely discover after acting: ownership, source authority, local
risk, stop-lines, and where proof must be obtained. Exact procedure is useful
only after the touched surface and validation lane are known. Making it
on-demand reduces recurring prompt cost without weakening the command source,
the package validator, or the blocking lane.

Keeping commands out of README preserves the public front door and avoids
turning human explanation into an operational catalog. Keeping machine
sequences in the existing lane manifest avoids a second executable authority.
The three roles therefore stay distinct: inherited semantic constraint,
on-demand human procedure, and machine-executed topology.

## Consequences

- Positive: inherited agent chains retain owner and safety meaning while
  shedding unrelated command and reading procedure.
- Positive: exact validation remains discoverable through one explicit route
  and enforceable through the existing manifest, validators, and CI runners.
- Positive: README files remain useful to people and public consumers instead
  of becoming hidden prompt dependencies.
- Tradeoff: an agent must follow one on-demand hop before executing a focused
  validation command.
- Tradeoff: validators and route-token tests that froze command prose inside
  `AGENTS.md` must be changed source-first rather than weakened or deleted.
- Follow-up: mechanically process every tracked `AGENTS.md`, `README.md`, and
  affected validation route; regenerate derived views only from their source;
  then report corpus counts, mandatory-read bytes, inherited-chain metrics,
  links, tests, and any owner ambiguity before integration.
- A green source check proves only its declared contract. It does not prove
  deployed runtime state, service health, artifact admission, external CI,
  review, merge, or sibling-owner acceptance.

## Source surfaces

- `AGENTS.md`
- `DESIGN.AGENTS.md`
- `README.md`
- `docs/routes/START_HERE_ROUTE_CONTRACT.md`
- `docs/validation/COMMAND_AUTHORITY.md`
- `docs/validation/validation_lanes.json`
- `VALIDATION.md`
- `docs/governance/RELEASING.md`
- `scripts/validation_lanes.py`
- `scripts/ci_gate.py`
- `scripts/validate_nested_agents.py`

## Follow-up route

Apply this decision across the tracked README/AGENTS corpus without deleting or
renaming those files in the mechanical lane. Preserve every unique runtime,
host-exposure, secret, storage, lifecycle, repair, deployment, proof, approval,
and sibling-owner stop-line. Revisit the decision only if measured prompt cost
cannot be reduced without losing those boundaries or if a stronger command
authority replaces the lane manifest.
