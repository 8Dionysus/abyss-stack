# Fail-Closed Source-Root Binding for Parity-Aware Helpers

- Decision ID: ABYSS-STACK-D-0136
- Status: accepted
- Date: 2026-08-23
- Owner surface: `mechanics/governed-execution/parts/autonomy-status/`, `mechanics/diagnostic-spine/parts/diagnose-wrapper/`, and `mechanics/governed-execution/parts/governed-runner/`

## Index Metadata

- Original date: 2026-08-23
- Surface classes: source/runtime boundary, runtime route contract
- Stack lanes: source checkout, runtime mirror, diagnostics
- Mechanic parents: governed-execution, diagnostic-spine
- Guard families: source identity, source/runtime boundary, fail-closed routing
- Posture: accepted bounded source-binding rationale

## Context

Parity-aware status, diagnostic, and governed-runner helpers used combinations
of a weak source shape, prefix/substring owner markers, and implicit home,
policy-default, or `STACK_ROOT` candidates. A foreign checkout could therefore
look like `abyss-stack`, or a deployed/projection invocation could select a
different dirty or stale tree. The resulting parity or governed-execution
evidence could name a different source tree from the canonical current source
without making route drift visible.

## Options considered

- Keep the home-directory fallback and rely on the existing source-shape
  markers.
- Keep each consumer's source predicate local while making the owner contract
  exact and removing implicit fallback candidates.
- Introduce a shared helper imported by all three consumers.
- Use a new runtime-written canonical source manifest containing path, ref, and
  tree identity.
- Discover source candidates under the shared workspace and reject only when
  they conflict.
- Combine an exact owner contract with explicit operator binding, constrained
  source-local discovery, projection rejection, and fail-closed unresolved
  behavior when no binding is available.

## Decision

Use the exact-contract route. `AOA_SOURCE_ROOT` is the authoritative explicit
operator binding. Without it, status and diagnosis may use only their own
`abyss-stack` source checkout, and governed execution may use only its own
owner-qualified source checkout. A valid candidate must have the required
source shape, exact first non-empty `README.md` line `# abyss-stack`, and exact
line 'Root route card for `abyss-stack`.' within the first eight `AGENTS.md`
lines. Runtime `Configs`, home-directory, policy-default, `STACK_ROOT`,
sibling, and workspace discovery are not implicit candidates. Invalid or
absent binding yields `source_root_unresolved` (or the governed-runner
equivalent fail-closed error) rather than a fallback path.

## Rationale

The selected route removes the ambiguity with the smallest source-local
change, preserves relocation through the existing environment contract, and
adds no host-specific path rail or deployment writer. Local exact predicates
are intentionally repeated: the three consumers are directly executed from
different mechanic paths and a shared import would require a new bootstrap or
`sys.path` dependency across source and runtime projections, increasing route
coupling and scans for a tiny contract. A runtime manifest could carry stronger
ref/tree currentness, but no bounded install/projection contract currently
writes and validates one; using an existing runtime receipt would confuse
projection/package evidence with source authority. Workspace discovery would
still have to adjudicate multiple branches and stale worktrees. Exact binding
plus constrained local discovery is deterministic, cheap, explainable, and
honest about the remaining currentness limit.

## Consequences

- Positive: dirty or stale `~/src/abyss-stack` cannot be selected silently by
  parity-aware status or diagnostic fallback paths.
- Positive: explicit overrides remain supported and invalid overrides cannot be
  masked by another candidate.
- Positive: forged suffix, prefix, substring, foreign same-shape, policy-default,
  `HOME`, `STACK_ROOT`, and projection candidates fail closed across all three
  consumers.
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
- `mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py`
- `mechanics/governed-execution/parts/governed-runner/README.md`
- `mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md`
- `mechanics/governed-execution/parts/governed-runner/tests/`

## Follow-up route

Use the governed-execution and diagnostic-spine focused tests plus source-fast
validation. If deployment later publishes a source identity manifest, route
that design through config-projection and parity owners and keep this
fail-closed behavior as the fallback.
