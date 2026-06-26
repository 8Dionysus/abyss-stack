# EVAL RUNTIME SEAM

This document describes the runtime-facing `aoa-evals` landing inside `abyss-stack`.

It is intentionally bounded:
- read-only eval selection and inspection via `/evals/*`
- filesystem-first private export candidates under `Logs/eval-exports/`
- filesystem-first private A2A return dry-run candidates under `Logs/a2a-return-closeouts/`
- one targeted runtime sidecar proof for the memo contradiction evidence family
- no general verdict loop
- no judge runtime
- no promotion or publication back into `aoa-evals`

## What is mirrored from `aoa-evals`

The deployed runtime may carry a public-safe mirror under:

- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals`

That mirror is created with:

```bash
scripts/aoa-sync-federation-surfaces --layer aoa-evals
```

The sync wrapper writes a runtime-local manifest at:

- `${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals/manifest/federation_mirror_manifest.json`

The manifest records source commit when available, generated time, required
files, compact counts, and file digests. It is freshness evidence only; the
mirror remains a read cache below `aoa-evals` source truth.

Freshness is checked with:

```bash
scripts/aoa-sync-federation-surfaces --check --json --layer aoa-evals
```

When the source checkout `HEAD` differs from the manifest
`source_git_commit`, the check returns `status:"stale"` and exits non-zero.
Operator-side maintenance may repair that explicit stale state with:

```bash
scripts/aoa-sync-federation-surfaces --check --sync-if-stale --json --layer aoa-evals
```

This keeps MCP/read surfaces from mutating owner mirrors while still giving
post-landing automation a safe refresh path.

The current allowlist includes:
- selected docs such as `TRACE_EVAL_BRIDGE.md` and `RUNTIME_BENCH_PROMOTION_GUIDE.md`
- generated eval catalog, capsules, sections, comparison spine, and report index surfaces
- public-safe example payloads for runtime evidence selection, including the
  workhorse, return-anchor, memo recall rerun, and memo contradiction evidence
  templates
- the public-safe schemas that define those payloads

`abyss-stack` treats this mirror as a read-only contract surface.
The mirror exists to support runtime-local inspection, selection, and bounded export preparation without turning the runtime into the authority layer.

## What `/evals/*` exposes

The localhost-only `route-api` exposes a bounded `/evals/*` namespace on top of the mirrored `aoa-evals` pack.

Raw read surfaces:
- `GET /evals/catalog`
- `GET /evals/capsules`
- `GET /evals/comparison-spine`

Structured advisory read surfaces:
- `POST /evals/inspect`
- `POST /evals/expand`
- `POST /evals/select`
- `POST /evals/comparison`
- `POST /evals/runtime-evidence-template`
- `POST /evals/hook-template`

These endpoints:
- read only mirrored runtime-local data
- do not call sibling repos directly
- do not compute verdicts
- do not execute tasks
- do not trigger export side effects

## Filesystem-first eval export candidates

The eval export landing adds two private runtime export wrappers:
- `aoa-export-runtime-evidence-selection`
- `aoa-export-artifact-hook-candidate`

The A2A return dry-run lane adds one private closeout wrapper:
- `aoa-a2a-return-closeout-dry-run`

The memo contradiction evidence family also has one bounded sidecar runner:
- `aoa-run-memo-contradiction-integrity`

These scripts read candidate payloads from `--input-file`, attach mirrored `aoa-evals` contract references, and write private runtime-owned wrapper artifacts under:

- `${AOA_STACK_ROOT}/Logs/eval-exports/latest/runtime-evidence-selection/`
- `${AOA_STACK_ROOT}/Logs/eval-exports/latest/artifact-hook/`
- `${AOA_STACK_ROOT}/Logs/eval-exports/records/`
- `${AOA_STACK_ROOT}/Logs/a2a-return-closeouts/`

The outputs are not `aoa-evals` objects.
They are bounded runtime candidates waiting for later review or export.
MCP candidate validation is even earlier: it only confirms that a proposed
packet is schema-shaped and review-routed before any filesystem export or
bundle-local review.
The `aoa_evals` MCP service may now list these private export records and read
one record for review routing. Listings omit nested private candidate payloads
by default. Reading or validating a record still does not accept evidence,
compute a verdict, or create an `aoa-evals` report.
The memo contradiction sidecar is narrower: it reads log-backed selected memo evidence plus generated `aoa-memo` object surfaces and emits a schema-shaped report for review; it does not publish or promote that report.
The A2A return dry-run wrapper is similarly narrow: it reads a reviewed
`aoa-sdk` closeout payload, exposes the clean local `a2a-return-closeout`
request family, preserves older SDK wire input only through the single
federation compatibility bridge, keeps `dry_run=true` and
`live_automation=false`, and assembles only a runtime receipt candidate plus
memo/eval handoff hints.

Example usage:

```bash
aoa-export-runtime-evidence-selection \
  --input-file /tmp/runtime-evidence-selection.json \
  --write

aoa-export-artifact-hook-candidate \
  --input-file /tmp/artifact-hook.json \
  --write

aoa-a2a-return-closeout-dry-run \
  --input-file /srv/AbyssOS/aoa-sdk/examples/a2a/reviewed_closeout_request.example.json \
  --write

aoa-run-memo-contradiction-integrity \
  --memo-root "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo" \
  --evals-root "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals"
```

## What this landing intentionally does not do

This seam does not:
- run local evals
- run general local evals
- execute A2A child routes
- calculate verdicts
- calculate general verdicts
- choose promotion outcomes
- publish into `aoa-evals`
- alter `langchain-api` request or response behavior
- add a second federation sidecar or new host port

`abyss-stack` only owns the runtime mirror, the localhost-only `/evals/*` inspection seam, and the bounded private export wrappers.
`aoa-evals` remains the authority for eval meaning and proof posture.
