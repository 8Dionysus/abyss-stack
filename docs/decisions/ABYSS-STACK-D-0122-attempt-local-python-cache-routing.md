# Attempt-Local Python Cache Routing

- Decision ID: ABYSS-STACK-D-0122
- Status: proposed
- Date: 2026-08-14
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`

## Index Metadata

- Original date: 2026-08-14
- Surface classes: external actor runtime, workspace hygiene, validation
- Stack lanes: governed execution, validation, review
- Mechanic parents: governed-execution
- Guard families: projection containment, exact argv identity, attempt isolation
- Posture: proposed runtime invariant pending independent review

## Context

External Codex writers use a runtime-owned actor projection as their complete
workspace delta. Landing profiles already suppress ordinary Python and pytest
cache output through a specialized environment, but generic writer profiles do
not receive that environment. `PYTHONDONTWRITEBYTECODE` also does not constrain
explicit `py_compile`, so a fixed validation turn can leave bytecode or pytest
cache paths in the projection and make an otherwise bounded return
authority-blocked. Resuming the same thread must not reuse the prior attempt's
scratch coordinate.

## Options considered

- Add environment assignments to each owner-signed validation command. This
  would change the exact argv identity and break retained validation receipts.
- Depend on `PYTHONDONTWRITEBYTECODE` and profile-specific pytest options. This
  leaves explicit `py_compile` output and generic writer profiles uncovered.
- Derive one runtime-owned Python hygiene map from each attempt scratch
  coordinate and inject it through the Codex shell environment policy. This
  keeps validation argv unchanged while placing all implicit imports, explicit
  compile output, and pytest cache controls outside the projection.

## Decision

For every admitted external Codex attempt, the runtime derives a
`PYTHONPYCACHEPREFIX` under the distinct attempt-local scratch directory and
injects it, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`, and
`PYTEST_ADDOPTS=-p no:cacheprovider` into both the process environment and the
validated Codex shell environment map. The runtime owns the coordinate; task
text, model commands, and owner-signed validation argv do not select it.

## Rationale

The actor projection remains the only mutable repository surface and the
complete final manifest therefore cannot contain Python or pytest cache
artifacts. A runtime-derived prefix handles the explicit-compile case that
bytecode suppression cannot. Applying the map at the runtime boundary covers
generic and specialized profiles alike, while keeping fixed validation
identity mechanically recognizable and preserving `validation_command_id`
receipts. Scratch-derived prefixes also separate initial and resumed attempts
without widening workspace authority.

## Consequences

- Positive: ordinary imports, explicit `py_compile`, and pytest cache behavior
  are contained outside the actor projection for every admitted profile.
- Positive: fixed validation argv and command IDs remain unchanged and
  independently auditable.
- Tradeoff: each attempt owns a small runtime scratch cache that must be
  retained long enough for final observation and cleanup by the surrounding
  lifecycle.
- Follow-up: independent review must inspect the exact source diff and focused
  lifecycle tests before any release, activation, or blocked-duty reproof.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_workspace_hygiene.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`
- `CHANGELOG.md`

## Follow-up route

The external Codex owner reviewer should verify the focused lifecycle evidence,
then route the proposed repair to the goal master for review filtering. Source
landing, artifact trust admission, activation, and blocked-duty reproof remain
separate owner decisions.
