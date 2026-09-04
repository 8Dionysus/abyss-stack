# AGENTS.md

Local route card for `mcp/services/aoa-evals-mcp/`.

## Purpose

`aoa-evals-mcp` is the thin MCP access plane for OS Abyss bounded proof
surfaces. It lets agents select, inspect, expand, compare, check runtime
  freshness, find-or-propose eval-need routes, validate candidate evidence packet
shape, expose the Eval Forge front door, read stack-owned runtime candidate
exports, and prepare candidate evidence/report skeletons without turning MCP
into proof authority. A separately authenticated candidate process exposes
only the explicitly gated repo-local port writers.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, source discovery, CLI, smoke tests, and service
  packaging for `aoa_evals`.
- The adapter boundary between `aoa-evals` generated readers, runtime-candidate
  readers, and Codex/OS Abyss access.
- Read-only find-or-propose routing into `aoa-evals` `eval_need_v1` authoring
  protocol.
- Candidate-only report skeleton and runtime evidence template helpers.
- Read-only Eval Forge access packet over readiness, candidate queue, local
  ports, route commands, and stop-lines.
- Read-only runtime status and schema-backed candidate packet validation.
- Read-only metadata/detail access for private stack-owned runtime candidate
  exports under `Logs/eval-exports/`.
- Listing, inspection, dry-run planning, and gated local writes for sibling
  repo `evals/` ports.
- Read-only consumption of the `aoa-evals` local-port inventory v2 suite
  execution projection; MCP may expose `absent`, `invalid`, `stale`, or
  source-contract-ready posture but may not execute `runner.argv` or write
  `evals/suites/*.suite.json` sidecars.
- Local-port writes limited to `evals/intake/*.eval_need.json`,
  `evals/suites/*.suite.md`, `evals/reports/*.report.md`, and `PORT.yaml`
  `skeleton` to `active` activation when the same write adds first pressure.

It does not own:

- eval bundle claims, verdict logic, report contracts, or proof authority;
- generated reader source truth;
- runtime evidence acceptance;
- receipt publication or bundle promotion.
- central `aoa-evals` bundle creation from MCP;
- sibling repo proof doctrine, verdict logic, scoring, or regression gates.

## Conditional source route

Read only the source, README, and owner contract needed for the current touched surface; entering this subtree does not require an unconditional inventory.

## Route Modes

| Need | First route |
| --- | --- |
| MCP resource, tool, or prompt shape | `src/aoa_evals_mcp/server.py` |
| source/generated reader access | `src/aoa_evals_mcp/core.py` |
| proof authority or stop-lines | `aoa-evals:docs/architecture/AOA_EVALS_MCP_CONTRACT.md` |
| eval birth proposal routing | `src/aoa_evals_mcp/core.py` and `aoa-evals:mechanics/proof-object/parts/eval-authoring/` |
| candidate runtime evidence posture | `aoa-evals:mechanics/audit/parts/candidate-readers/` |
| stack runtime candidate exports | `abyss-stack:mechanics/governed-execution/parts/candidate-exports/` and `Logs/eval-exports/` |
| source/mirror freshness | `src/aoa_evals_mcp/core.py` and `mechanics/federation-seams/parts/sync-wrapper/aoa_sync_federation_surfaces.sh` |
| Eval Forge access packet | `src/aoa_evals_mcp/core.py` and `aoa-evals:generated/eval_readiness_dashboard.json` |
| report skeleton behavior | `src/aoa_evals_mcp/core.py` and source bundle report contract |
| repo-local eval ports | `src/aoa_evals_mcp/core.py` and `aoa-evals:docs/guides/LOCAL_EVAL_PORT_STANDARD.md` |
| Codex-plane registration | `8Dionysus:config/codex_plane/runtime_manifest.v1.json` |
| admitted capability profiles | `aoa-evals:docs/architecture/aoa_evals_mcp_capabilities.v1.json` and `src/aoa_evals_mcp/organ_access.py` |

## AGENTS Stack Law

- MCP exposes access; it does not promote proof.
- Forge access packets are read-only routing evidence; they must not accept
  worksheets, promote candidates, or write local/central proof.
- Generated readers and MCP responses stay weaker than bundle-local `EVAL.md`
  and `eval.yaml`.
- Runtime evidence templates stay candidate-only until bundle-local review.
- Local eval-port writes stay below central `aoa-evals` proof authority and
  must dry-run before `apply=true`.
- V1 or unknown local-port inventory input must never infer runnable posture;
  injected suite execution fields fail closed to `absent`.
- Keep stdio as the portable default. Optional shared Streamable HTTP must stay
  authenticated and loopback-only under `ABYSS-STACK-D-0077`; wider exposure
  still requires a later decision.

## Run

In the shared AoA Codex plane this service is registered as `aoa_evals` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. Use the workspace
launcher from the shared root when testing the registered route; use [VALIDATION.md](../../../VALIDATION.md).

For source-local service execution from the `abyss-stack` repo root, use the on-demand validation route in `VALIDATION.md`.


Set `AOA_EVALS_MCP_CAPABILITY_PROFILE` to one exact owner capability only for a
profiled contour. The allowed pairs are read with `eval-discovery-read` or
`proof-result-read`, and candidate with `eval-request-prepare`. The owner
manifest must be present and must bind the exact runtime catalog.

The first command defaults to the read contour. Candidate writes additionally
require `AOA_EVALS_MCP_CANDIDATE_ROOTS`; managed lifecycle supplies the exact
root and systemd write allowlists.

If the package is installed, use the installed server entry-point procedure in `VALIDATION.md`.


## Report

State which MCP surface changed, which `aoa-evals` contract or reader it
exposes, what validation ran, and whether runtime exposure, source mutation,
proposal approval, verdict computation, receipt publication, or proof authority
changed.
