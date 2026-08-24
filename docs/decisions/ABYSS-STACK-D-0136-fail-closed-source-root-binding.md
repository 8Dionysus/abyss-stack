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
evidence could name a different source tree from the intended source without
making route drift visible. The first repair removed path fallback but still
left a same-shape foreign worktree accepted by all three consumers because
identity stopped at marker shape.

## Options considered

- Keep the home-directory fallback and rely on the existing source-shape
  markers.
- Keep each consumer's source predicate local while making the owner contract
  exact and removing implicit fallback candidates.
- Introduce a shared, stdlib-only pure helper loaded from each executing source
  root without a `sys.path` or bootstrap dependency.
- Use a caller-supplied content-addressed source contract containing exact Git
  `HEAD`/tree coordinates and selected source-surface digests.
- Use normalized path plus device/inode capture and final revalidation to close
  resolve/use replacement races.
- Use a new runtime-written canonical source manifest containing path, ref, and
  tree identity.
- Discover source candidates under the shared workspace and reject only when
  they conflict.
- Combine an exact owner contract with explicit operator binding, constrained
  source-local discovery, projection rejection, and fail-closed unresolved
  behavior when no binding is available.

## Decision

Use a content-addressed identity contract across all three consumers. The
`abyss_stack_source_identity_v1` contract carries the target, exact Git `HEAD`
and tree object IDs, selected source-surface SHA-256 digests (including the
shared helper and invoking consumer when present), and a canonical content
seal. `AOA_SOURCE_ROOT` remains only a lookup coordinate; an explicit root must
be paired with an absolute shared `AOA_SOURCE_IDENTITY` receipt covering the
three consumers, and a governed request may carry the same exact contract in
`source_identity` (or its runner-specific selected surfaces). Without an explicit
contract, a consumer may derive the current identity only from its executing
source root. This preserves legitimate isolated worktrees while rejecting a
foreign same-shape checkout that has no caller-provided identity.

Every binding still requires the exact source shape, exact first non-empty
`README.md` line `# abyss-stack`, and exact line 'Root route card for
`abyss-stack`.' within the first eight `AGENTS.md` lines. Runtime `Configs`,
home-directory, policy-default, `STACK_ROOT`, sibling, and workspace discovery
are not implicit candidates. Relative paths, `/proc/self/cwd`, and symlink
aliases are accepted only when the resolved root matches the explicit identity
contract. Bindings capture device/inode and revalidate the identity immediately
before source use, so source replacement or resolve/use TOCTOU fails closed.
Invalid or absent binding yields `source_root_unresolved` (or the
governed-runner equivalent fail-closed error) rather than a fallback path.

## Rationale

The selected route compares identity rather than location. Exact Git
`HEAD`/tree coordinates distinguish commits, selected source digests cover the
working-tree surfaces that each consumer can execute, and the canonical JSON
content seal prevents a receipt from being edited into a different contract.
The normalized device/inode pair closes root replacement after resolution, while
the final digest/coordinate observation closes content replacement before use.

One shared stdlib-only helper is loaded by absolute path relative to the
executing source root and deliberately has no repository imports. This avoids a
new bootstrap or `sys.path` dependency while keeping the identity predicate
identical across the diagnostic wrapper, autonomy status, and governed runner.
Source-local derivation is restricted to that executing root, not any path that
happens to have the same markers. Explicit receipts retain relocation and
legitimate isolated worktrees without introducing a brittle canonical-path
rail. The path/dev/inode check is a race detector, not the source authority;
content identity remains the authority. Sub-second p50/p95 measurements are a
performance guard only, not a security proof.

## Consequences

- Positive: dirty or stale `~/src/abyss-stack` cannot be selected silently by
  parity-aware status or diagnostic fallback paths.
- Positive: explicit overrides remain supported only with a valid exact identity
  receipt, and invalid overrides cannot be masked by another candidate.
- Positive: forged suffix, prefix, substring, foreign same-shape, alias,
  replacement, policy-default, `HOME`, `STACK_ROOT`, and projection candidates
  fail closed across all three consumers unless an exact caller-supplied
  identity contract binds the selected root.
- Positive: legitimate isolated worktrees remain usable when their caller
  supplies the exact current identity; no canonical path is required.
- Tradeoff: a deployed `Configs` helper without `AOA_SOURCE_ROOT` now reports a
  source-input truth gap and cannot run a source parity check until an operator
  supplies both the root coordinate and identity receipt.
- Limit: the binding identifies an owner-qualified source input and selected
  content surfaces; it does not prove remote currentness, deployment, runtime
  health, trust admission, or semantic acceptance.
- Follow-up: revisit a manifest-based route only when install/projection owns a
  validated current ref/tree identity record and its consumer contract; do not
  replace this with a path-only canonical rail.

## Source surfaces

- `docs/runtime/PATHS.md`
- `scripts/abyss_stack_source_identity.py`
- `mechanics/governed-execution/parts/autonomy-status/aoa_status_autonomy.py`
- `mechanics/governed-execution/parts/autonomy-status/README.md`
- `mechanics/diagnostic-spine/parts/diagnose-wrapper/aoa_diagnose.py`
- `mechanics/diagnostic-spine/parts/diagnose-wrapper/README.md`
- `mechanics/governed-execution/parts/governed-runner/aoa_governed_execution.py`
- `mechanics/governed-execution/parts/governed-runner/README.md`
- `mechanics/governed-execution/parts/governed-runner/docs/GOVERNED_EXECUTION.md`
- `mechanics/diagnostic-spine/parts/diagnose-wrapper/tests/test_aoa_diagnose.py`
- `mechanics/governed-execution/parts/autonomy-status/tests/test_aoa_status_autonomy.py`
- `mechanics/governed-execution/parts/governed-runner/tests/`

## Follow-up route

Use the governed-execution and diagnostic-spine focused tests plus source-fast
validation. The focused adversarial tests must retain same-shape foreign,
relative/symlink alias, source replacement, and final revalidation coverage for
all three consumers. If deployment later publishes a source identity manifest,
route that design through config-projection and parity owners and keep this
fail-closed content contract as the fallback.
