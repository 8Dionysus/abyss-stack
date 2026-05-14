# 2026-05-13 Root Residual Topology Cleanup

Status: accepted
Date: 2026-05-13

## Context

After the larger mechanics and root design passes, two source-safe but
misplaced route surfaces still flattened the repository root:

- `AUDIT.md` was a repo-wide review contract living beside entrypoint and
  policy files.
- `Spark/` was an agent fast-loop lane living as if it were a runtime district.

Both were useful, but their root placement worked against the intended
topology: root files should route, `docs/` should carry repo-wide documentation
contracts, and `.agents/` should carry repo-local agent overlays.

## Options considered

1. Keep `AUDIT.md` and `Spark/` as root districts.
2. Delete the useful material because the root placement was wrong.
3. Move the audit contract and Spark lane to their owning districts with validator coverage.

## Decision

Move the audit contract to `docs/AUDIT.md`.

Move the Spark fast-loop lane to `.agents/spark/`.

Add validator coverage so the old root paths do not quietly return.

## Rationale

Both surfaces were useful, so deletion would lose signal. Their problem was placement: audit is repo-wide documentation law, while Spark is an agent lane. Moving them into `docs/` and `.agents/` keeps the signal and removes root flatness.

## Consequences

- The repository root stays reserved for entrypoint, governance, policy, and
  standard GitHub-facing files.
- Agent model lanes now live under `.agents/<lane>/`, which keeps them
  separate from runtime, docs, scripts, and mechanics districts.
- Repo-wide audit expectations remain source-controlled and indexed from
  `docs/README.md`.
- The change does not alter live runtime state, host exposure, secrets mapping,
  service lifecycle, or deployed Configs parity.

## Source surfaces

- `docs/AUDIT.md`
- `.agents/spark/`
- `docs/README.md`
- `.agents/README.md`
- `scripts/validate_stack.py`

## Follow-up route

Route future root residuals to the smallest owning district before adding new root folders or root files.
