# Compose Independent Codex Hook Fragments

- Decision ID: ABYSS-STACK-D-0103
- Status: accepted
- Date: 2026-07-29
- Owner surface: `mechanics/config-projection/parts/codex-hooks/`

## Index Metadata

- Original date: 2026-07-29
- Surface classes: config projection, Codex hooks, sibling owner seam
- Stack lanes: source, runtime, operator
- Mechanic parents: config-projection
- Guard families: owner boundary, atomic projection, rollback, content minimization
- Posture: accepted source-local composition rationale, unlanded and inactive

## Context

The OS-user Codex configuration already contains standalone
`aoa-session-memory` hooks. `aoa-memo` now needs its own independently owned
participation-shadow fragment. Both hook families can match the same Codex
events, while the native user surface is one `hooks.json`.

Making either repository render the other's hook would introduce the wrong
dependency and let one owner overwrite a valid standalone configuration.
Copying both families manually would make ordering, duplicate detection,
backup, rollback, and exact source identity unverifiable.

## Options considered

- Make `aoa-session-memory` import and render the memo hook.
- Make `aoa-memo` replace the existing session-memory hook config.
- Keep separate files and rely on Codex source discovery to merge them
  implicitly.
- Add a neutral stack-owned compositor that accepts independent native or
  owner-envelope fragments.

## Decision

Add a `config-projection` part that accepts explicitly ordered fragments,
validates the current command-only Codex hook shape, resolves only declared
safe absolute-path bindings, rejects unresolved placeholders and exact
duplicate handlers, and emits one native config without owner-envelope
metadata.

Read-only rendering and exact-output comparison are the default. Explicit
write requires a receipt path, atomically replaces a mode-`0600` target,
preserves any previous bytes in a private backup, and restores the previous
target if receipt creation fails. The receipt stores fragment and output
digests plus binding-value digests, never raw binding paths or hook content.

The compositor owns no hook semantics. `aoa-memo` and
`aoa-session-memory` remain standalone repositories with separate skills,
hooks, tests, and lifecycle. Their cooperation is configuration coexistence,
not a runtime or source dependency.

## Rationale

Config projection is the narrow owner for turning multiple public-safe source
definitions into one runtime-readable file. It can preserve exact inputs,
ordering, atomicity, backup, and rollback without becoming the owner of memory
meaning or session evidence.

This also makes removal symmetric: either fragment can be omitted and the
remaining standalone config can be rendered and restored without editing the
other repository.

## Consequences

- Native session-memory output remains a valid input without an envelope.
- Memo can publish and evolve its own fragment independently.
- Duplicate or unresolved definitions fail before a candidate is written.
- Composition receipts prove exact config construction, not Codex trust,
  invocation, skill selection, memory use, outcome, or benefit.
- Live `~/.codex/hooks.json` activation and trust remain separate,
  operator-visible gates.

## Source surfaces

- `mechanics/config-projection/parts/codex-hooks/`
- `mechanics/config-projection/PARTS.md`
- `mechanics/config-projection/PROVENANCE.md`
- `docs/decisions/AOA-MEM-D-0083` in the `aoa-memo` owner repository

## Follow-up route

Validate the compositor with the unchanged standalone session-memory native
config and the exact memo-owned H0 fragment. Produce a candidate and receipt
outside the live Codex config. Only after held-out hook, skill, and eval checks
may an exact trusted definition be activated reversibly.
