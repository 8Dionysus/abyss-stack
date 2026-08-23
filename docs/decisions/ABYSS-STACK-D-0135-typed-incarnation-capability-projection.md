# Typed Incarnation Capability Projection

- Decision ID: ABYSS-STACK-D-0135
- Status: proposed
- Date: 2026-08-23
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`

## Index Metadata

- Original date: 2026-08-23
- Surface classes: runtime containment, public contract, source/runtime boundary
- Stack lanes: governed-execution, runtime, validation
- Mechanic parents: governed-execution
- Guard families: capability projection, grant freshness, terminal identity
- Posture: proposed runtime rationale

## Context

The operator-visible external incarnation must retain ordinary task continuity
and actor tooling without inheriting every capability carried by the ambient
Codex home. The prior projection linked all non-local ambient entries, which
made operator-control state such as app-server control, hooks, queues, and
browser/plugin state indistinguishable from ordinary session continuity. A
separate live launch defect also allowed the parent admission path to reject a
holder before its Kitty ancestry and dedication binding had become observable.

## Options considered

- Keep linking every ambient entry and grow an endpoint-specific denylist.
- Rehome the visible holder entirely and lose the operator-visible continuity
  and terminal identity route.
- Project semantic capability classes with deny-by-default operator control,
  admit one exact owner grant when present, and wait for the causal terminal
  binding handshake before receipt publication.

## Decision

Use the third route. The v2 incarnation-home manifest records a model-neutral
projection for every non-local ambient entry. Only authored session continuity
and actor tooling classes are shared-link defaults; all other entries are
`unknown` and denied. An exact typed grant may declare one concrete entry as
operator control and project it only when its capability ID/effect,
ambient-home identity, model realization, incarnation coordinate, regular-file
digest, and future expiry all match the current incarnation. The runtime
validates the projection again when loading the manifest and preserves the
owner-authored capability-class registry plus grant path/digest as provenance
and drift evidence.

The visible holder retries the exact Kitty ancestry and dedicated-window
identity handshake for a bounded interval before writing its non-replacing
holder receipt. A timeout or missing identity fails closed; it cannot be
converted into a successful launch by a parent-only timeout extension.

## Rationale

Semantic classes preserve ordinary work while preventing ambient operator
control from becoming an implicit external-incarnation authority. The
owner-authored registry supplies the class meaning and leaves entries absent
from it as explicit `unknown`, so adding a future capability family does not
grow executable endpoint special cases. Deny-by-default unknown entries avoid
implicit authority while exact grants provide a typed future extension point.
The grant is intentionally reusable by its exact subject until expiry; subject,
path, grant-artifact digest, and expiry binding make copied, stale, or mutated
grant artifacts fail closed, but mutable bytes inside a dynamic operator
endpoint are not target-content-bound. The causal wait repairs the observed
race at the receipt publication seam, where the payload process is the only
source that can bind its own exact holder identity through the installed
wrapper.

## Consequences

- Positive: the runtime materializes only the intended home projection and
  exposes a durable typed grant surface for future owner policy.
- Positive: holder receipt publication now depends on the same causal terminal
  identity that visible launch admission later validates.
- Tradeoff: app-server mutation enforcement remains outside this source slice;
  the projection is not semantic owner policy, live protection, or acceptance.
- Residual: installed release parity, host trust/admission, a live canary,
  wake delivery, holder closure, semantic re-entry, and Goal acceptance remain
  separate follow-up evidence.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/capability-classes.v1.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-incarnation-home.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-capability-classes.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-capability-grant.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_visible_incarnation_home.py`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`

## Follow-up route

The external-codex owner and release/host owner must validate the installed
schema projection, trust admission, and live visible launch before treating
this source implementation as active protection. The app-server owner must
add and prove the effect-boundary grant intersection separately; this runtime
manifest does not authorize that mutation by itself.
