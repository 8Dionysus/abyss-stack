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
- Guard families: complete selection, exact partition proof, serial rollback
- Posture: accepted bounded parallel scheduling; no coverage reduction

## Context

The complete repository gate initially collected 2,194 tests, four skips, and
230 subtests. On landed `main`, pytest alone took 899.36 seconds while the
source validators before it took only a few seconds. The public GitHub runner
provides four CPUs, so one serial pytest process dominated the landing path.

The corpus is not uniform. It contains real subprocess and governed-execution
scenarios, and one source file contributes more than 600 tests. Whole-file
sharding leaves a serial tail. Independent GitHub jobs duplicate setup and
would need a separate sufficiency graph before they could replace one atomic
suite verdict.

Controlled full-selection comparisons included xdist `load` with two, three,
and four workers; xdist `worksteal`; eight and 32 isolated-process shards; a
hybrid serial/xdist split; file-aware process shards; and duration-aware queue
ordering. The best xdist local trial passed in 269.82 seconds, and the public
runner passed the exact PR head in 351.94 seconds. That runner also emitted 157
warnings because the governed external-agent tests call `os.fork()` inside
multithreaded xdist workers. The forked child continues Python execution, so
the warning represented a real deadlock boundary rather than harmless output.

The isolated-process comparisons retained one pytest process per active shard.
Eight coarse shards were green but needed about 471 seconds; 32 hash-distributed
shards needed 382.54 seconds. Keeping small files as import units and splitting
only large files reduced that to 321.14 seconds. Starting measured slow units
first then completed the current 2,200-test candidate, four skips, and 230
subtests in 269.61 seconds, with a 517.7 MiB cgroup memory peak and no swap or
multithreaded-fork warning. The hybrid split was stopped after 403 seconds when
its serial fork-sensitive lane was still incomplete and could no longer beat
the already green process-DAG result.

The first exact-head process-scheduler CI run proved an exact 2,205-test union
and exposed two test-harness defects previously masked by serial timing and
import order. One isolated test referenced `unittest.mock` without importing
that submodule. One terminal-state polling helper discarded a valid
`authority_blocked` transition that occurred at its deadline: its diagnostic
read saw the completed state, but it raised unconditionally. The repair imports
`mock` explicitly and performs one final authoritative state observation at
the polling boundary without extending the timeout or weakening the expected
authority result. A local isolated-environment run also exposed one fixture
that resolved a virtual-environment interpreter symlink before starting a
bubblewrap child, thereby discarding that environment's dependencies. Passing
the exact `sys.executable` preserves the admitted interpreter environment.

## Options considered

- Retain the serial gate and optimize only individual tests.
- Split files or scopes statically across processes or GitHub jobs.
- Use xdist `load` with two, three, or four workers.
- Use xdist `worksteal` with four bounded workers.
- Run one serial fork-sensitive lane beside xdist for the remaining tests.
- Run bounded, process-isolated shards with exact union proof.
- Use an unbounded worker count derived from every visible logical CPU.

## Decision

The complete default `tests` and `release` selections run through
`scripts/run_pytest_lane.py`. Automatic mode uses at most four independent
pytest processes and a queue of 32 deterministic file-aware shards. Small test
files stay in one import unit; only files larger than the target shard size are
split. Conservative duration hints start known slow units first. Hints affect
queue order only and cannot alter membership or verdict.

Before execution, one collect-only process writes the ordered baseline nodeids,
count, and digest. The scheduler proves that all assignments are disjoint and
their union equals that baseline. Every child receives explicit nodeids, writes
its observed-selection manifest and exit receipt, and must match its assignment
exactly. The aggregate is green only when every child is green and every
selection proof is exact. Failed shard logs are replayed after the aggregate so
bounded CI and resource-launch log tails retain the actionable traceback even
when an early shard fails and later shards continue to completion.

Targeted pytest arguments use the unchanged serial path automatically. An
explicit process scheduler refuses targeted arguments rather than inventing a
second partition contract. `ABYSS_STACK_TEST_SCHEDULER=serial` remains the exact
full-selection rollback and independent sequential oracle.

## Rationale

The chosen scheduler matches the four-CPU runner while avoiding xdist's
controller thread inside test processes. It therefore preserves the real
`os.fork()` scenarios without accepting a scheduler-created deadlock risk. Its
measured 269.61-second local result matches the fastest xdist trial while using
only stdlib orchestration plus pytest already required by the suite.

File-aware shards remove most repeated imports. Dynamic queueing avoids the
large-file tail, and duration hints close the remaining scheduling imbalance.
Because baseline, assignment, observation, and aggregate proof are independent
of the hints, future timing drift can only reduce speed; it cannot hide tests.
A bounded count also prevents accidental fan-out on high-core developer hosts.

## Consequences

- Positive: the entire assertion surface remains blocking while the dominant
  local and CI critical path executes concurrently.
- Positive: the scheduler has an explicit Claim/Evidence DAG: baseline claim,
  disjoint shard evidence, observed-selection receipts, and one atomic verdict.
- Positive: fork-sensitive tests run in process-isolated pytest children and no
  longer inherit an xdist control thread.
- Positive: process isolation makes order-dependent imports and polling-boundary
  races visible; both remain blocking failures until repaired and re-proved.
- Positive: an early failed shard remains diagnosable from the final bounded
  log tail, avoiding a second full run merely to recover its traceback.
- Positive: no extra scheduler dependency is installed, and exact serial
  execution remains one environment switch away.
- Tradeoff: each shard is a fresh pytest process, so import cost is higher than
  persistent workers; file-aware units bound that cost.
- Tradeoff: timing hints need occasional refresh as slow-test topology changes,
  but stale hints affect performance only.
- Follow-up: require green exact-head PR and postmerge runs on the public runner,
  compare repeat distributions, and use the serial oracle before classifying a
  scheduler-specific failure.

## Source surfaces

- `scripts/run_pytest_lane.py`
- `docs/validation/validation_lanes.json`
- `docs/validation/COMMAND_AUTHORITY.md`
- `docs/testing/TEST_TOPOLOGY.md`
- `.github/workflows/validate-stack.yml`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/runtime-lifecycle/parts/logs-status/tests/test_optimization_audit_status.py`

## Follow-up route

The next validation pass should use GitHub timings and shard receipts to refresh
duration hints or decompose remaining long subprocess tests. A future multi-job
DAG must still prove the same complete selection and final sufficiency; it must
not replace the serial oracle or hide failed owner evidence.
