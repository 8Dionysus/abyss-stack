# Fail-Closed Source-Root Binding for Parity-Aware Helpers

- Decision ID: ABYSS-STACK-D-0136
- Status: accepted
- Date: 2026-08-23
- Owner surface: `mechanics/governed-execution/parts/autonomy-status/` and `mechanics/diagnostic-spine/parts/diagnose-wrapper/`

## Index Metadata

- Original date: 2026-08-23
- Surface classes: source/runtime boundary, runtime route contract
- Stack lanes: source checkout, runtime mirror, diagnostics
- Mechanic parents: governed-execution, diagnostic-spine
- Guard families: source identity, source/runtime boundary, fail-closed routing
- Posture: accepted bounded source-binding rationale

## Context

Parity-aware status and diagnostic helpers accepted an explicit
`AOA_SOURCE_ROOT`, then their executing source checkout, and finally
`~/src/abyss-stack`. When the helper ran from the deployed `Configs` projection
with no explicit binding, that last candidate silently selected a dirty and
stale checkout. The resulting parity evidence could name a different source
tree from the canonical current source without making the route drift visible.

## Options considered

- Keep the home-directory fallback and rely on the existing source-shape
  markers.
- Use a new runtime-written canonical source manifest containing path, ref, and
  tree identity.
- Discover source candidates under the shared workspace and reject only when
  they conflict.
- Combine explicit operator binding with owner-qualified source-local
  discovery, reject deployed projections, and fail closed when no binding is
  available.

## Decision

Use the fourth option. `AOA_SOURCE_ROOT` is the authoritative explicit
operator binding. Without it, a helper may use only its own `abyss-stack`
source checkout when the owner markers and source shape are present. Runtime
`Configs`, home-directory, sibling, and workspace discovery are not implicit
candidates. Invalid or absent binding yields `source_root_unresolved` rather
than a fallback path.

## Rationale

The selected route removes the ambiguity with the smallest source-local
change, preserves relocation through the existing environment contract, and
adds no host-specific path rail or deployment writer. A runtime manifest could
carry stronger ref/tree currentness, but no bounded install/projection contract
currently writes and validates one; using an existing runtime receipt would
confuse projection/package evidence with source authority. Workspace discovery
would still have to adjudicate multiple branches and stale worktrees. Explicit
binding plus constrained local discovery is deterministic, cheap, explainable,
and honest about the remaining currentness limit.

## Consequences

- Positive: dirty or stale `~/src/abyss-stack` cannot be selected silently by
  parity-aware status or diagnostic fallback paths.
- Positive: explicit overrides remain supported and invalid overrides cannot be
  masked by another candidate.
- Tradeoff: a deployed `Configs` helper without `AOA_SOURCE_ROOT` now reports a
  source-input truth gap and cannot run a source parity check until an operator
  supplies the binding.
- Limit: the binding identifies an owner-qualified source input; it does not
  prove remote currentness, deployment, runtime health, or semantic acceptance.
- Follow-up: revisit a manifest-based route only when install/projection owns a
  validated current ref/tree identity record and its consumer contract.

## Source surfaces

- `docs/runtime/PATHS.md`
- `mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py`
- `mechanics/governed-execution/parts/autonomy-status/README.md`
- `mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py`
- `mechanics/diagnostic-spine/parts/diagnose-wrapper/README.md`

## Follow-up route

Use the governed-execution and diagnostic-spine focused tests plus source-fast
validation. If deployment later publishes a source identity manifest, route
that design through config-projection and parity owners and keep this
fail-closed behavior as the fallback.
