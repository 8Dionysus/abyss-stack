# 2026-05-13 Root Residual Topology Cleanup

## Status

Accepted.

## Context

After the larger mechanics and root design passes, two source-safe but
misplaced route surfaces still flattened the repository root:

- `AUDIT.md` was a repo-wide review contract living beside entrypoint and
  policy files.
- `Spark/` was an agent fast-loop lane living as if it were a runtime district.

Both were useful, but their root placement worked against the intended
topology: root files should route, `docs/` should carry repo-wide documentation
contracts, and `.agents/` should carry repo-local agent overlays.

## Decision

Move the audit contract to `docs/AUDIT.md`.

Move the Spark fast-loop lane to `.agents/spark/`.

Add validator coverage so the old root paths do not quietly return.

## Consequences

- The repository root stays reserved for entrypoint, governance, policy, and
  standard GitHub-facing files.
- Agent model lanes now live under `.agents/<lane>/`, which keeps them
  separate from runtime, docs, scripts, and mechanics districts.
- Repo-wide audit expectations remain source-controlled and indexed from
  `docs/README.md`.
- The change does not alter live runtime state, host exposure, secrets mapping,
  service lifecycle, or deployed Configs parity.
