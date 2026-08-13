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

A later postmerge profile showed why duration-aware reassignment alone had no
material headroom left. The 32 observed shard durations totalled 1,558.56
seconds, so the four-worker lower bound was 389.64 seconds; the actual queue
makespan was already about 391 seconds. Shards 1 through 9 all came from
`test_external_codex_agent.py` and accounted for about 87 percent of total
shard time. One representative end-to-end test executed 103 programs because
the exact five-probe Codex preflight runs once at admission and again in the
worker, as the runtime contract requires.

The next comparison therefore kept the scheduler, selection, and repeated
preflight unchanged and overlapped only independent probes inside each
preflight. On one fixed old-baseline wave of the first four slow shards, all
282 assigned tests and the exact observed union stayed green. Wall time fell
from 132.58 to 111.00 seconds (16.3 percent), cgroup CPU time fell from 398.81
to 365.63 seconds (8.3 percent), and memory peak rose from 636.6 to 701.1 MiB.
The result rejects a duration-hint-only change for this bottleneck and admits
the process-isolated preflight-overlap candidate to complete-suite and public
runner validation; it does not weaken or cache any runtime probe.

The subsequent complete local proof used the exact CI owner pins, an installed
`aoa-sdk` (so isolated `python -I` subprocesses exercised the packaged route),
and the unchanged 4-by-32 scheduler. Its exact union selected 2,220 tests and
closed green; after adding an explicit completed-sibling orphan-cleanup proof,
the final exact union selected 2,221 tests and closed with 2,217 passed, four
skipped, and 230 passed subtests in 318.99 seconds, with a 757.4 MiB cgroup
memory peak and no swap.

The independent public comparison rejected unconditional nested overlap as a
complete-suite optimization on the four-CPU runner. Two exact baseline runs
completed their pytest queues in 390.99 and 382.79 seconds. The overlap
candidate remained correctness-green but needed 411.10 seconds; its four-worker
queue was already within one second of the 410.32-second lower bound. The
regression is consistent with four outer pytest processes each creating up to
three inner probe processes. A local speedup on a larger host therefore does
not admit the same scheduling policy under a smaller outer CPU budget.

The next comparison separated transport proof from runtime-semantic proof
without changing production code, full-suite membership, or the repeated
worker preflight contract. Four explicit fixture cases retain the real
`_codex_preflight` path: executable pathname replacement, nested Codex sandbox,
missing role-scoped MCP credential, and the complete preflight/start/worker
lifecycle. The probe-group tests independently retain concurrent completion,
timeout cleanup, and completed-sibling descendant cleanup. Other lifecycle,
report, authority, and evidence tests install a successful contract-shaped
preflight double only on their fixture runtime. The runtime forks its worker,
so that double is inherited across the same admission and worker call sites;
tests that alter the second return still prove that worker revalidation occurs.
It does not add a runtime flag or a production bypass.

On the same fixed four-shard, 282-test local wave, the stratified candidate
passed the exact union in 96.08 seconds. That is 13.4 percent faster than the
111.00-second overlap-only candidate and 27.5 percent faster than the
132.58-second serial-preflight baseline. This admits stratification to the full
local and public gates; public-runner evidence remains required before landing.

Full-suite profiling then exposed two independent deterministic tests that
silently called the deployed `langchain-api /run/federated` advisory endpoint.
One Agent OS adapter chain spent about six seconds blocked in one socket receive
per successful governed closeout. Its 28-test file fell from 78.23 to 17.48
seconds after the test backend supplied a local contract-shaped review trace;
25 tests still passed and the same three explicitly live-compiler cases stayed
skipped. A governed-runner skipped-reasons test fell from 20.36 seconds to 0.03
seconds after receiving the same explicit test input. Neither test asserts live
advisory quality, and the default test contract already forbids dependence on
deployed runtime state. Dedicated live receipts remain the evidence for that
external surface.

Two complete post-change local runs selected the identical 2,221-node digest
and remained exact and green. The first completed in 281.28 seconds with
1,005.20 aggregate shard-seconds; the second completed in 316.63 seconds with
1,170.14 aggregate shard-seconds under materially different host contention.
The earlier overlap-only local proof was 318.99 seconds and 1,120.39
shard-seconds. The isolated causal comparisons are therefore accepted, but no
single local full-suite wall time is treated as a stable effect estimate; the
fresh public runner remains the landing comparison.

## Options considered

- Retain the serial gate and optimize only individual tests.
- Split files or scopes statically across processes or GitHub jobs.
- Use xdist `load` with two, three, or four workers.
- Use xdist `worksteal` with four bounded workers.
- Run one serial fork-sensitive lane beside xdist for the remaining tests.
- Run bounded, process-isolated shards with exact union proof.
- Overlap every independent preflight probe inside each outer shard.
- Keep production preflight exact while stratifying transport sentinels from
  semantic runtime tests through a fork-inherited fixture double.
- Let deterministic tests reach deployed advisory services and fall back after
  a network timeout.
- Supply contract-shaped advisory inputs inside tests whose claim is local
  review-packet or runtime semantics, retaining live service proof elsewhere.
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

The external Codex production runtime still executes every admitted probe and
repeats the complete preflight in the worker. Its independent probes may
overlap only as separate process groups with their existing timeout, cleanup,
and fail-closed results. Test fixtures separate that transport proof from
unrelated semantic assertions: named exact cases execute production preflight,
while the remaining cases replace only the fixture instance's successful
`_codex_preflight` result. No environment switch, launch field, runtime profile,
or installed surface can select the test double.

Default deterministic tests must likewise provide their advisory trace when
their assertion is about local runtime or review-packet semantics. They may not
probe a deployed service incidentally and then accept a timeout fallback as
test setup. Live advisory integration remains a separate explicit evidence
lane.

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
Once that queue is within one percent of its duration lower bound, further
scheduler tuning is not treated as the default answer: the owning slow test or
runtime operation must be profiled and changed under its own contract.

Inner concurrency is not free capacity. The public counterexample shows that a
locally faster nested fan-out can slow an already saturated four-worker queue.
Transport stratification removes repeated setup only where the test's claim is
about lifecycle or authority semantics, while explicit exact sentinels retain
the real containment and credential claims. This moves the test boundary
instead of weakening the runtime boundary.

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
- Positive: semantic external-agent tests retain admission/worker call topology
  without paying for five real transport probes at every unrelated assertion.
- Positive: exact preflight, nested sandbox, credential, timeout, cleanup, and
  full-lifecycle claims remain tied to real-process tests.
- Positive: deterministic Agent OS and review-packet tests no longer vary with
  deployed advisory health or wait through its network timeout.
- Positive: no extra scheduler dependency is installed, and exact serial
  execution remains one environment switch away.
- Tradeoff: each shard is a fresh pytest process, so import cost is higher than
  persistent workers; file-aware units bound that cost.
- Tradeoff: timing hints need occasional refresh as slow-test topology changes,
  but stale hints affect performance only.
- Tradeoff: a new test whose claim depends on live preflight must opt into the
  exact fixture path; reviews must reject a semantic double for that claim.
- Follow-up: require green exact-head PR and postmerge runs on the public runner,
  compare repeat distributions, and use the serial oracle before classifying a
  scheduler-specific failure.

## Source surfaces

- `scripts/run_pytest_lane.py`
- `docs/validation/validation_lanes.json`
- `docs/validation/COMMAND_AUTHORITY.md`
- `docs/testing/TEST_TOPOLOGY.md`
- `.github/workflows/validate-stack.yml`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`
- `mechanics/runtime-lifecycle/parts/logs-status/tests/test_optimization_audit_status.py`

## Follow-up route

The next validation pass should prove the stratified candidate on the public
runner and compare its exact queue against both baseline runs. If nested
oversubscription remains visible in the small exact layer, compare an explicit
outer-to-inner process budget before changing the default production overlap.
Then continue decomposing long subprocess tests instead of refreshing duration
hints without measured queue imbalance. A future multi-job DAG must still prove
the same complete selection and final sufficiency; it must not replace the
serial oracle or hide failed owner evidence.
