# Frontload Release Artifact Guard Before the Complete Suite

- Decision ID: ABYSS-STACK-D-0129
- Status: proposed
- Date: 2026-08-21
- Owner surface: `docs/validation/validation_lanes.json`

## Index Metadata

- Original date: 2026-08-21
- Surface classes: validation workflow, release gate, landing latency
- Stack lanes: validation, release, tests
- Mechanic parents: config-projection
- Guard families: fail-fast ordering, complete evidence, release artifact trust
- Posture: proposed ordering invariant pending independent review

## Context

The release lane runs several cheap deterministic source and artifact guards
before the complete pytest suite, but the runtime-config artifact bundle guard
was last. A failure in that guard therefore arrived only after the expensive
full-suite attempt and made the next repair pay the suite cost again. The guard
is a source-checkout validation of generated deployable outputs; it does not
require host deployment or live service state.

The direction requires reducing repeated real-session validation cost without
turning missing evidence into success, selecting tests by guess, or weakening
the release contract. The current release sequence and parity boundary are
manifest-owned, so the smallest owner-local change is an ordering invariant.

## Options considered

- Leave the artifact guard after pytest. This preserves evidence but needlessly
  delays a cheap deterministic failure until after the expensive suite.
- Remove or make the artifact guard advisory. This reduces time by dropping a
  required trust check and is rejected.
- Cache or reuse the artifact receipt across source changes. This requires a
  new exact-input identity and invalidation contract and is outside this slice.
- Run the existing artifact guard before pytest while retaining every command
  and the existing post-sequence parity step. This preserves sufficiency while
  shortening the failure-repair path for this known late guard.

## Decision

The manifest-owned `release_check` sequence runs
`validate_abyss_machine_runtime_config_bundle.py` before
`scripts/run_pytest_lane.py`. The complete pytest selection, its exact
partition/observation proof, every other release command, and synthetic/live
Configs parity behavior remain unchanged. The sequence still fails closed on
the first failed command and never treats a missing artifact or unknown state
as success.

## Rationale

The artifact guard is deterministic and bounded, while the full suite is the
dominant release cost on the public runner. Ordering the guard first changes
only when a known failure is observed; it cannot hide a passing or failing
test, and it does not assert that a local measurement is a universal
real-session speedup. The manifest remains the only command authority and a
focused regression locks the relative order and presence of both guards.

## Consequences

- Positive: an artifact-bundle failure returns before the full suite, avoiding
  a needless expensive restart during repair.
- Positive: all release evidence remains blocking and present, with parity
  still outside and after the manifest-backed sequence.
- Tradeoff: a passing artifact guard adds its small cost before pytest rather
  than after it; total successful release work is unchanged up to scheduling
  noise.
- Tradeoff: this does not reduce the cost of a pytest or external dependency
  failure and does not establish a universal wall-time improvement.
- Follow-up: compare exact-head hosted runs and later real-session receipts;
  consider receipt reuse or impact selection only with a separate complete
  input/invalidation contract.

## Source surfaces

- `docs/validation/validation_lanes.json`
- `docs/validation/COMMAND_AUTHORITY.md`
- `scripts/release_check.py`
- `mechanics/config-projection/parts/rendering/scripts/validate_abyss_machine_runtime_config_bundle.py`
- `tests/test_validation_command_authority.py`

## Follow-up route

The independent reviewer should verify the manifest diff, focused ordering
regression, and exact hosted release result. Runtime deployment, artifact
admission, real-session latency, and wider Goal acceptance remain separate
claims.
