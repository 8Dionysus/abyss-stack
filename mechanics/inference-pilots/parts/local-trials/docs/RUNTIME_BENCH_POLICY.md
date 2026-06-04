# RUNTIME BENCH POLICY

## Purpose
This document defines the bounded runtime-benchmark surface for `abyss-stack`.

It covers how local-model runtime benchmarks are created, named, stored, compared, and exported as evidence candidates.

It does not move agent-quality verdict logic into `abyss-stack`.

## Core rule
`abyss-stack` owns runtime benchmark evidence, not proof-layer meaning.

It may own:
- benchmark runners and runner-local fixtures for runtime behavior
- raw logs, traces, timing captures, memory samples, and normalized summary manifests
- storage layout and retention rules
- host, preset, profile, backend, and quantization context
- render-truth, smoke, and internal-probe references

It must not own:
- portable verdict wording about agent quality
- global model rankings
- hidden benchmark-to-quality scores
- proof-canon promotion decisions

## What counts as a runtime benchmark here
Use this surface for:
- cold start and model load posture
- first-token and end-to-end latency
- streaming throughput
- RAM, VRAM, and device pressure
- context-window stress under one bounded fixture family
- restart, health, and recovery behavior
- profile or preset parity under matched host conditions
- serving backend parity under matched host conditions

Do not use this surface for:
- general capability claims
- reasoning quality claims
- artifact quality judgments
- agent workflow truth
- benchmark theater based on one flattering prompt

## Canonical benchmark families
Keep `benchmark_family` bounded to one of:
- `startup-load`
- `latency-single-turn`
- `throughput-stream`
- `memory-pressure`
- `context-stress`
- `availability-recovery`
- `profile-parity`
- `backend-parity`

## Required run context
Every benchmark manifest should make these things explicit:
- the runtime selection: one `profile`, `preset`, or explicit profile set
- the system under test: backend, model label, `profile_class`, context budget class, quantization or runtime variant
- the host surface: OS, CPU, RAM, accelerator surface, optional vault mount state
- the runtime truth refs: rendered services or config refs, smoke ref, internal-probe ref when relevant
- the fixture surface: bounded case family, case count, input shape, and token budgeting assumptions
- the metric units and summary semantics
- the notes that say what the run does not prove

## Storage contract
Canonical active root:
- `${AOA_STACK_ROOT}/Logs/runtime-benchmarks`

Optional heavy-data root:
- `${AOA_VAULT_ROOT}/runtime-benchmarks`

Recommended active tree:
```text
${AOA_STACK_ROOT}/Logs/runtime-benchmarks/
  catalog.json
  retention.json
  cohorts.json
  latest/
    index.json
  runs/
    index.json
    2026-03-24T154200Z__latency-single-turn__workhorse-local-q4/
      benchmark.manifest.json
      summary.json
      notes.md
      probes/
      render/
      raw/
      plots/
  comparisons/
  latest/
```

Rules:
- keep the manifest and compact summary on the active runtime root
- move bulky raw captures to the optional vault when mounted
- never assume `${AOA_VAULT_ROOT}` exists just because the architecture names it
- never commit secret-bearing rendered config or live env material
- keep one generated catalog and one `latest/` pointer layer so repeated runs stay comparable without hand-scanning timestamp directories

## Minimum run outputs
A strong runtime benchmark run should produce:
- `benchmark.manifest.json`
- `summary.json`
- `notes.md`
- one or more refs to render-truth, smoke, or internal-probe outputs
- optional `raw/` captures
- optional `plots/` or small derived charts

`benchmark.manifest.json` is the machine-readable truth surface.

`summary.json` is the compact reader surface. It may be a projection of the manifest rather than a second source of truth.

`notes.md` carries human review notes, caveats, and non-claims.

## First bounded runner

For the current local Qwen path, use the runtime-local bench wrapper:

```bash
scripts/aoa-qwen-bench --profile local-worker
scripts/aoa-qwen-bench --preset intel-full
```

This runner stays on the intended `langchain-api /run` path and writes machine-local evidence under `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/runs/`.
It performs one uncounted warmup call per case before measured repeats so warm-latency reads stay warm by definition instead of by accident.

The default helper posture now targets the promoted local-worker path on `5403`.
Use explicit `--url`, `--backend-label`, `--runtime-variant`, and `--target-label` only when you are refreshing an explicit challenger packet or keeping historical comparison lineage readable. The current bounded posture does not treat a second local control lane as part of the canonical operator path.

Refresh the durable catalog after new runs:

```bash
scripts/aoa-runtime-bench-index
```

That helper writes:
- `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/catalog.json`
- `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/retention.json`
- `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/cohorts.json`
- `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/latest/index.json`
- `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/runs/index.json`

Retention classes:
- `canonical`
  Current latest pointers and the latest run for each active target label.
- `historical`
  Older runs that remain part of an active lineage or older comparison/promotion history.
- `exploratory`
  Local evidence that is not part of the current default comparison surface.

Cohort layer:
- `current-control`
  Historical cohort label retained for older comparison packets; current canonical reading starts from the promoted `llama.cpp` runs on `5403`.
- `promotion-basis`
  The runs directly used by the current comparison/promotion verdict path.
- `current-promoted`
  The latest promoted winner runs for the active backend substrate.
- `comparison-challenger`
  The latest challenger runs retained beside the promoted winner.
- `historical-baseline`
  Older comparison runs kept for lineage and drift review.

## Relationship to local trial programs

If you need a supervised per-case trial program rather than a standalone
benchmark run, route through [LOCAL_AI_TRIALS](LOCAL_AI_TRIALS.md). The old
step-gated command sequence is preserved only as a compatibility baseline
routed through the local-trials compatibility runner.

That helper may reuse runtime benchmark artifacts as evidence inside case packets, but it does not change the benchmark boundary:

- benchmark artifacts remain runtime-local truth in `abyss-stack`
- trial-step verdicts remain bounded trial judgments, not portable eval canon
- portable proof wording still belongs in `aoa-evals`

## Optional backend-parity pilot

For historical drift review or explicit challenger maintenance around the promoted `llama.cpp` path, use:

```bash
scripts/aoa-llamacpp-pilot run --preset intel-full
```

That pilot writes a bounded comparison packet under `${AOA_STACK_ROOT}/Logs/runtime-benchmarks/comparisons/`. Historical packet lineage may still carry earlier baseline naming from the pre-cutover pilot family, but the canonical operator path stays on `5403`.

Use the catalog layer to answer:
- what the latest canonical run was for a target label
- which comparison packet currently represents a pilot family
- which promotion packet currently represents the active substrate verdict

For the reviewed operator loop that turns a candidate packet into a live winner
decision, use
[RUNTIME_WINNER_PROMOTION_LOOP](../../promotion-loop/docs/RUNTIME_WINNER_PROMOTION_LOOP.md).
That note owns the operator sequence from fresh machine-fit through candidate
packet, promotion decision, adaptation record, and live re-check.

## Comparison hygiene
Before treating two runs as comparable, keep stable:
- host hardware class or disclose the delta
- benchmark family
- bounded fixture family
- backend path or disclose the delta
- metric semantics and units
- profile or preset selection, or disclose the delta
- model target and runtime variant, or disclose the delta

Name these changes explicitly when they move:
- driver or runtime stack
- container image version
- service exposure posture
- prompt or fixture changes
- token budgeting or stop conditions

If those surfaces drift materially, treat the result as:
- local exploration
- or noisy variation

Do not turn it into a clean before-vs-after read.

## Promotion boundary
What may travel upward toward `aoa-evals`:
- selected normalized summaries
- explicit environment notes
- bounded comparison notes
- compact case breakdowns when they remain reviewable

What must stay local:
- raw uncurated dumps
- secret-bearing rendered config
- private host details that should not leave the runtime
- broad claims about capability or intelligence

## Naming discipline
Prefer benchmark IDs shaped like:
- `local-workhorse-q4-startup`
- `intel-deep-q6-context-stress`
- `ollama-vs-ovms-latency-peer`

Keep the run directory name readable:
`<timestamp>__<benchmark-family>__<target-label>`

## Non-goals
This surface is not:
- a proof canon
- a leaderboard
- a hidden global score
- a shortcut around `aoa-evals`
- a substitute for human review

## Hook surface
Use `../mechanics/inference-pilots/parts/local-trials/schemas/runtime-benchmark.schema.json` as the machine-readable manifest contract.

Use `../mechanics/inference-pilots/parts/local-trials/examples/runtime_benchmark.workhorse-local.example.json` as the first bounded example.

## Boundary to preserve
`abyss-stack` may measure the body's behavior.

It does not decide what that behavior means beyond bounded runtime posture.
