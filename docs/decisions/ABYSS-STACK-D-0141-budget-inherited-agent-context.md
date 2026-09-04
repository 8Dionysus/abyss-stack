# Budget Inherited Agent Context

- Decision ID: ABYSS-STACK-D-0141
- Status: accepted
- Date: 2026-08-30
- Owner surface: `AGENTS.md`, `DESIGN.AGENTS.md`, and `scripts/validate_nested_agents.py`

## Index Metadata

- Original date: 2026-08-30
- Surface classes: agent guidance, MCP access plane, validation contract
- Stack lanes: source, MCP services, validation
- Mechanic parents: none
- Guard families: nested AGENTS, inherited context, route locality
- Posture: accepted source-route rationale; no runtime admission or exposure change

## Context

The tracked README/AGENTS corpus contained 59 unique inherited AGENTS chains.
Two MCP service chains exceeded the 32-KiB low-context budget:
`aoa-session-memory-mcp` at 34,907 bytes and `aoa-evals-mcp` at 33,524 bytes.

The leaf cards already owned their exact run, smoke, verification, owner, and
stop-line contracts. The excess came from `mcp/AGENTS.md` and
`mcp/services/AGENTS.md` repeating the command matrix for every sibling
service. An agent entering one service therefore inherited unrelated commands
twice before reaching the correct local card.

## Options considered

- Keep both parent command matrices and accept the recurring prompt cost.
- Move executable commands into human-facing MCP README maps.
- Keep package-specific commands in the nearest service card, keep one broad
  district lane in each parent, and make inherited-chain size a blocking
  validator contract.

## Decision

Choose the third option.

`mcp/AGENTS.md` and `mcp/services/AGENTS.md` remain route cards. They point to
the human package map, the nearest service-local card, and the existing
`mcp-services` district lane. Each service-local `AGENTS.md` remains the source
for exact package commands and local stop-lines.

`scripts/validate_nested_agents.py` enforces a 32-KiB inherited-chain budget
for every discovered `AGENTS.md`, including required, legacy, and not-yet-
modeled cards. The budget is a navigation and context guard; it does not make
short guidance more authoritative than complete local law.

## Rationale

This route follows `DESIGN.AGENTS.md`: parent cards establish ownership and
route selection, while proximity narrows to exact action. It removes unrelated
procedure from descendant context without deleting any service-local command
or moving operational detail into a human entry map. Applying the budget to
all discovered cards prevents a new unmodeled subtree from bypassing the
guard.

## Consequences

- Positive: the two over-budget chains fall below 32 KiB, and all MCP services
  inherit a smaller parent route.
- Positive: exact package checks and owner stop-lines remain beside the package
  they validate.
- Tradeoff: an agent changing an MCP package must follow one explicit hop from
  the district card to the service-local card.
- Follow-up: the cross-repository README/AGENTS corpus ledger remains the
  integration surface for detecting new pressure outside this owner.
- A green command or budget check proves only its declared source contract; it
  does not prove deployed service state, admission, proof, or owner acceptance.

## Source surfaces

- `AGENTS.md`
- `DESIGN.AGENTS.md`
- `mcp/AGENTS.md`
- `mcp/services/AGENTS.md`
- `mcp/services/README.md`
- `scripts/validate_nested_agents.py`
- `docs/validation/VALIDATOR_TOPOLOGY.md`

## Follow-up route

Run `python scripts/validate_nested_agents.py` after route-card topology
changes. Use `python scripts/ci_gate.py --mode mcp-services` only for a
district-wide MCP change; package work should start with the exact service-local
route. Revisit the limit only with measured corpus evidence and a replacement
that preserves owner boundaries and stop-lines.
