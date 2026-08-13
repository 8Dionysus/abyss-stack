# Validation Command Authority

`abyss-stack` keeps validation commands in one source-authored manifest:

```text
docs/validation/validation_lanes.json
```

`scripts/validation_lanes.py` loads and validates that manifest.
`scripts/ci_gate.py` executes named lanes.
`scripts/release_check.py` remains the source release entrypoint and parity
stabilizer, but it reads the release command sequence from the lane manifest.

## Balance

| Surface | Role |
|---|---|
| `docs/validation/validation_lanes.json` | executable lane command sequences |
| `scripts/validation_lanes.py` | stdlib loader/API and manifest validation |
| `scripts/ci_gate.py` | local and CI lane executor |
| `scripts/run_pytest_lane.py` | bounded scheduler for the unchanged complete pytest selection |
| `scripts/release_check.py` | release entrypoint plus synthetic/live Configs parity selection |
| `.github/workflows/validate-stack.yml` | GitHub platform runner that calls lane entrypoints and owns platform-only rehearsal steps |
| `AGENTS.md` and local route cards | focused validation guidance and lane IDs |
| inventories under `docs/validation/` and `docs/testing/` | descriptive coverage maps, not command execution authority |

## Rules

- Do not store a second release command list in workflow YAML, tests, README
  text, or `release_check.py`.
- Do not make inventories executable authority. They should explain coverage
  and failure routes.
- Do not make `source-fast` perform source/runtime parity, synthetic Configs
  rehearsal, live service checks, or release-only stabilization.
- Keep `.github` platform rehearsal public-safe and source-checkout-only.
- Keep live parity opt-in through `scripts/release_check.py --parity-mode live`.
- Keep OS Abyss artifact bundle checks in the release lane when they validate
  generated deployable outputs rather than source topology alone.
- Keep full-suite scheduling bounded and reversible. Automatic mode may use
  four process-isolated workers over an exact file-aware partition. Baseline,
  disjoint union, observed selection, and child exit receipts must all verify;
  `ABYSS_STACK_TEST_SCHEDULER=serial` is the explicit rollback. Timing hints may
  change order, never selection or failure semantics.

## Active Lanes

| Lane | Purpose |
|---|---|
| `source-fast` | growth-safe route, decision, nested AGENTS, stack topology, and local stats contract checks |
| `generated` | generated decision, diagnostic read-model, and vendored MCP HTTP auth helper freshness |
| `tests` | default pytest collection for current source checkout contracts, scheduled through the bounded full-suite runner |
| `mechanics-part-local` | mechanic part-local pytest homes, including currently active provenance tests |
| `mcp-services` | MCP service validators and service-local tests |
| `shellcheck` | shell wrapper/backend syntax hygiene where shellcheck is available |
| `release` | full source release command sequence before Configs parity stabilization |

## Failure Route

When a command fails, fix the owning source surface named by the lane and
inventory before editing the lane manifest. Change the manifest only when the
boundary, command owner, or lane meaning changes.
