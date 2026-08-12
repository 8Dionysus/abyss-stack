# Schedule Full Pytest With Bounded Work Stealing

- Decision ID: ABYSS-STACK-D-0120
- Status: accepted
- Date: 2026-08-12
- Owner surface: `docs/validation/validation_lanes.json`

## Index Metadata

- Original date: 2026-08-12
- Surface classes: validation workflow, test scheduler, landing latency
- Stack lanes: validation, tests, release
- Mechanic parents: none
- Guard families: complete selection, exact dependency pin, serial rollback
- Posture: accepted bounded parallel scheduling; no coverage reduction

## Context

The complete repository gate collected 2,194 tests, four skips, and 230
subtests. On the landed `main` postmerge run, pytest alone took 899.36 seconds;
the source validators before it took only a few seconds. The workflow therefore
spent almost its entire critical path inside one serial pytest process even
though the public GitHub runner provides four CPUs.

The suite is not a uniform unit-test corpus. It contains many real subprocess
and governed-execution scenarios, while one source file alone contributes more
than 600 tests. Scheduling by whole file or scope would leave a large serial
tail, and splitting the suite into several GitHub jobs would duplicate setup
and weaken the simplicity of one complete selection unless a separate
sufficiency graph were introduced.

Controlled full-selection trials compared xdist `load` with two, three, and
four workers, then four-worker `worksteal`. All candidates passed the same
2,194 tests, four skips, and 230 subtests. The measured pytest wall times were
480.49 seconds, 382.10 seconds, 356.93 seconds, and 278.44 seconds
respectively. A second four-worker work-stealing run passed in 269.82 seconds.
Observed unit memory peaks rose from about 846 MiB at two workers to about
1.15-1.22 GiB at four workers.

## Options considered

- Retain the serial gate and optimize only individual tests.
- Split files or scopes statically across processes or GitHub jobs.
- Use xdist `load` with two, three, or four workers.
- Use xdist `worksteal` with four bounded workers.
- Use an unbounded worker count derived from every visible logical CPU.

## Decision

The complete `tests` and `release` selections run through
`scripts/run_pytest_lane.py`. Automatic mode admits four-worker xdist
`worksteal` only when installed `pytest-xdist` is exactly `3.8.0`. A missing or
different pin falls back to the unchanged serial selection. Explicitly asking
for the parallel scheduler with a missing or different pin fails closed.

`ABYSS_STACK_TEST_SCHEDULER=serial` selects the exact serial rollback and
independent sequential oracle. Scheduling changes order only: it does not
change collection roots, markers, skips, retries, assertions, exit status, or
failure interpretation.

## Rationale

Four-worker work stealing matched the public runner's bounded CPU shape and
removed the long tail better than xdist's ordinary load scheduler. Repeated
full-suite success provides stronger evidence than a targeted smoke, while the
exact dependency pin prevents a silently changed scheduler implementation from
entering the owner gate.

The serial fallback preserves availability for minimal local environments and
keeps rollback immediate. A bounded count avoids turning a high-core developer
host into an accidental unbounded subprocess fan-out. Static file and scope
sharding remain valid future methods if the large-file topology is first
decomposed or a source-owned sufficiency graph can prove complete selection.

## Consequences

- Positive: the entire assertion surface remains blocking while the dominant
  local and CI critical path can execute concurrently.
- Positive: exact serial execution remains one environment switch away and is
  also the safe automatic fallback when the scheduler pin is unavailable.
- Positive: selection stays centralized in pytest instead of being copied into
  workflow job shards.
- Tradeoff: the release environment installs one exact scheduler dependency
  and uses roughly 1.2 GiB at the measured four-worker peak.
- Tradeoff: test order is intentionally nondeterministic across workers, so a
  test that depends on shared mutable state should fail and be repaired rather
  than silently forced green.
- Follow-up: require green PR and postmerge runs on the public four-CPU runner,
  monitor later runs for scheduler-specific flakes, and use the serial oracle
  before classifying any such failure.

## Source surfaces

- `requirements-dev.txt`
- `scripts/run_pytest_lane.py`
- `docs/validation/validation_lanes.json`
- `docs/validation/COMMAND_AUTHORITY.md`
- `docs/testing/TEST_TOPOLOGY.md`
- `.github/workflows/validate-stack.yml`

## Follow-up route

The next validation pass should compare repeat run distributions on GitHub and
inspect the remaining long subprocess tests. Static/DAG decomposition should
be reconsidered only with an explicit complete-selection and final-sufficiency
contract; it must not replace the serial oracle or hide failed owner evidence.
