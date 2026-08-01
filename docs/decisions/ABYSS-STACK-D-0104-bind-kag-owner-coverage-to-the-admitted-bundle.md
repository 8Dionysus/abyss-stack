# Bind KAG Owner Coverage to the Admitted Bundle

- Decision ID: ABYSS-STACK-D-0104
- Status: accepted
- Date: 2026-08-01
- Owner surface: `mechanics/federation-seams/parts/kag-seam/`

## Index Metadata

- Original date: 2026-08-01
- Surface classes: runtime contract, federation seam, retrieval eval
- Stack lanes: source, runtime, validation
- Mechanic parents: federation-seams
- Guard families: owner boundary, bundle identity, coverage, fail closed
- Posture: accepted source-local runtime validation rationale

## Context

The repo-self KAG retrieval eval kept a second hard-coded expected owner count.
After `aoa-kag` correctly removed two non-provider repositories from its
provider registry, the verified 21-owner bundle and all three live projections
agreed, but the stack eval still expected 23 owners and failed only its
`owner_coverage` threshold.

The failure was useful: it prevented admission. The duplicated count was not a
valid long-term authority boundary, because `aoa-kag` owns provider membership
while `abyss-stack` owns materialization and runtime verification.

## Options considered

- Replace the hard-coded count with 21 and repeat the same cross-owner drift on
  the next legitimate membership change.
- Read the live `aoa-kag` provider registry directly from the stack eval,
  coupling runtime verification to a sibling checkout.
- Remove or weaken the coverage threshold and trust aggregate counts.
- Derive the exact expected owner-name set from the verified bundle metadata
  already materialized into the SQLite projection, then compare both exact and
  lexical per-owner cases to that set.

## Decision

The repo-self retrieval eval derives its expected owner names from the
`canonical_inputs` bound into the active verified bundle identity. It requires
the exact and lexical case owner sets to equal that canonical set.

The eval rejects missing, empty, malformed, or duplicate canonical owner
inputs. Its config continues to own retrieval thresholds and curated semantic
cases, but no longer duplicates provider membership or an expected owner
count.

## Rationale

The bundle is the exact handoff from the stronger KAG owner into the stack
runtime. Binding coverage to its canonical inputs verifies the runtime object
the stack actually admitted without making `abyss-stack` a second provider
registry or adding a live sibling-checkout dependency.

Comparing owner names rather than only counts also rejects substitution: an
unrelated owner cannot replace a missing owner while preserving the same
cardinality. Keeping the threshold fail-closed preserves the useful rollout
stop that exposed the stale assumption.

## Consequences

- Legitimate provider membership changes require a new verified bundle and a
  full projection bootstrap, but no stack source edit solely to change a
  number.
- Exact and lexical coverage must include every and only canonical bundle
  owner.
- Malformed or duplicate bundle membership fails before a passing receipt can
  be written.
- `aoa-kag` remains the provider-membership owner; the stack remains the
  runtime materialization and verification owner.
- Historical fixed-size composition references remain historical context, not
  current runtime law.

## Source surfaces

- `mechanics/federation-seams/parts/kag-seam/aoa_kag_runtime_eval.py`
- `mechanics/federation-seams/parts/kag-seam/config/repo-self-retrieval-eval.json`
- `mechanics/federation-seams/parts/kag-seam/tests/test_kag_runtime_projection.py`
- `mechanics/federation-seams/parts/kag-seam/docs/KAG_RUNTIME_SEAM.md`
- `mcp/services/aoa-kag-mcp/DESIGN.md`

## Follow-up route

Run the retrieval eval against the exact membership-changed bundle, then keep
KAG shadow until source landing, deployed Configs parity, current and
last-known-good canaries, consumer observation, central proof, owner
acceptance, and rollback projection all bind to the landed revisions.
