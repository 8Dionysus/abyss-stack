# Holder-Local Incarnation Mutable State

- Decision ID: ABYSS-STACK-D-0136
- Status: proposed
- Date: 2026-08-23
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`

## Index Metadata

- Original date: 2026-08-23
- Surface classes: runtime containment, public contract, source/runtime boundary
- Stack lanes: governed-execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: capability projection, incarnation identity, concurrency isolation
- Posture: proposed runtime rationale

## Context

The typed capability projection correctly denied ambient operator-control and
unknown entries, but the home lifecycle treated every non-local ambient name as
if it were a managed shared link. A Codex-created regular file or SQLite sidecar
under a denied ambient name was therefore either reported as projection-link
drift during repeated `prepare` or as an unexpected top-level home entry during
manifest loading. The realization-scoped home also gave sequential holders the
same mutable top-level namespace, so one duty could poison the next one.

## Options considered

- Add filename-specific exceptions for the observed database and sidecar names.
- Permit arbitrary actor-local top-level state in the projected home.
- Derive actor-local state from the current typed denied projection and give
  every newly created holder a digest-bound mutable namespace, while retaining
  marked legacy v2 homes for compatibility.

## Decision

Use the third route. The runtime records the derived denied-entry set as
`actor_local_state_names`; those entries may be absent or materialize as
regular files/directories owned by the actor, but never as symlinks or special
files. Shared entries continue to require an exact symlink to the ambient
source. A prior shared symlink may be removed only when the current typed
projection demotes that entry to denied; a regular local shadow is preserved.

New homes require an opaque holder namespace whose digest selects a holder-local
directory below the realization coordinate. Repeated preparation with that
namespace is idempotent, while distinct namespaces cannot share mutable Codex
state. A missing namespace remains valid only when an existing legacy v2
ownership marker selects the old realization-scoped path.

## Rationale

The denied set is an owner-authored semantic projection, not a hardcoded list of
filenames. This preserves default-deny even when Codex creates a local file with
the same basename as ambient operator-control state. The top-level type check
keeps unknown links and arbitrary special entries outside the actor-local
surface. A holder coordinate makes concurrency explicit and durable without
putting actor, task, Goal, version, or path identity into policy.

## Consequences

- Positive: repeated prepare accepts legitimate denied local state without
  converting it into shared authority.
- Positive: distinct holders retain separate mutable databases, sidecars, and
  lock directories while preserving realization-bound grants.
- Tradeoff: callers creating a new home must supply a stable unique namespace;
  old marked v2 homes remain a compatibility case until retired by their owner.
- Residual: source behavior and installed-artifact parity remain separate from
  host trust admission, live canary evidence, transport delivery, and owner
  acceptance.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-incarnation-home.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/README.md`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/DIRECTION.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

The external-Codex runtime owner must validate the installed content-addressed
release and a bounded live canary. The host artifact owner must admit the exact
release subject before activation. No step here grants app-server effect
authority, owner acceptance, master wake, or Goal completion.
