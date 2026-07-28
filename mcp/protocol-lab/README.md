# MCP Protocol Lab

This district holds the source-side compatibility gate for an OS Abyss MCP
protocol migration. It does not select a new production protocol merely
because a specification, SDK, or client advertises support.

Current posture on 2026-07-26:

- production wire version: `2025-11-25`;
- next candidate: `2026-07-28-RC`;
- next migration: blocked;
- stable registration: `aoa_kag`;
- isolated future lab registration: `aoa_kag_next_lab`, disabled;
- first pilot: compact read-only `aoa-kag`;
- candidate and effect organs: excluded.

The matrix pins exact specification, SDK, conformance-suite, and consumer
observations. The pair observation records which runtime receipts actually
exist. The generated status is derived from both and remains fail-closed until
all fourteen P1 gates pass.

## Source map

| Surface | Meaning |
|---|---|
| `protocol-compatibility-matrix.v1.json` | authored stable/next comparison, exact pins, gates, alias and pilot law |
| `fixtures/current-pair-observation.json` | current evidence-backed pair observation |
| `schemas/` | machine-readable input and derived-status contracts |
| `generated/protocol-lab-status.json` | deterministic, rebuildable migration verdict |
| `scripts/build_protocol_lab_status.py` | pure status builder |
| `scripts/validate_protocol_lab.py` | fail-closed source and stack-pin validator |
| `tests/` | mutation and migration-gate tests |

Read [CONTRACT.md](CONTRACT.md) for admission law and
[docs/COMPATIBILITY_MATRIX.md](docs/COMPATIBILITY_MATRIX.md) for the refresh
workflow.
