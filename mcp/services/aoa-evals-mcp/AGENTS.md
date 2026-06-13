# AGENTS.md

Local route card for `mcp/services/aoa-evals-mcp/`.

## Purpose

`aoa-evals-mcp` is the thin MCP access plane for OS Abyss bounded proof
surfaces. It lets agents select, inspect, expand, compare, check runtime
freshness, find-or-propose eval-need routes, validate candidate evidence packet
shape, read stack-owned runtime candidate exports, and prepare candidate
evidence/report skeletons without turning MCP into proof authority. It also
federates sibling repository `evals/` ports and can perform explicitly gated
repo-local port writes.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, source discovery, CLI, smoke tests, and service
  packaging for `aoa_evals`.
- The adapter boundary between `aoa-evals` generated readers, runtime-candidate
  readers, and Codex/OS Abyss access.
- Read-only find-or-propose routing into `aoa-evals` `eval_need_v1` authoring
  protocol.
- Candidate-only report skeleton and runtime evidence template helpers.
- Read-only runtime status and schema-backed candidate packet validation.
- Read-only metadata/detail access for private stack-owned runtime candidate
  exports under `Logs/eval-exports/`.
- Listing, inspection, dry-run planning, and gated local writes for sibling
  repo `evals/` ports.
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

## Start Here

1. `README.md`
2. `DESIGN.md`
3. `docs/BOUNDARIES.md`
4. `docs/THREAT_MODEL.md`
5. `src/aoa_evals_mcp/core.py`
6. `src/aoa_evals_mcp/server.py`
7. `tests/`

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
| report skeleton behavior | `src/aoa_evals_mcp/core.py` and source bundle report contract |
| repo-local eval ports | `src/aoa_evals_mcp/core.py` and `aoa-evals:docs/guides/LOCAL_EVAL_PORT_STANDARD.md` |
| Codex-plane registration | `8Dionysus:config/codex_plane/runtime_manifest.v1.json` |

## AGENTS Stack Law

- MCP exposes access; it does not promote proof.
- Generated readers and MCP responses stay weaker than bundle-local `EVAL.md`
  and `eval.yaml`.
- Runtime evidence templates stay candidate-only until bundle-local review.
- Local eval-port writes stay below central `aoa-evals` proof authority and
  must dry-run before `apply=true`.
- Keep the server stdio-only unless a later decision widens exposure.

## Run

In the shared AoA Codex plane this service is registered as `aoa_evals` through
`8Dionysus:config/codex_plane/runtime_manifest.v1.json`. Use the workspace
launcher from the shared root when testing the registered route:

```bash
/srv/AbyssOS/.codex/bin/aoa-evals-mcp-server.py
```

For source-local service execution from the `abyss-stack` repo root, run:

```bash
python mcp/services/aoa-evals-mcp/scripts/aoa_evals_mcp_server.py
```

If the package is installed, the server entry point is:

```bash
aoa-evals-mcp-server
```

## Smoke

```bash
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli catalog
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli select --proof-question "bounded change verification"
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli find-or-propose --proof-question "bounded change verification"
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli inspect aoa-bounded-change-quality
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli expand aoa-bounded-change-quality --section-key intent
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli runtime-evidence-template aoa-bounded-change-quality
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli runtime-status
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli validate-evidence-candidate --candidate-file /tmp/runtime-evidence-selection.json
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli runtime-candidate-exports --limit 5
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli local-ports
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli local-port aoa-memo
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli find-or-propose-local aoa-memo --proof-question "repo-local eval pressure"
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli report-skeleton aoa-bounded-change-quality --evidence-ref artifact:example
```

## Verify

```bash
python mcp/services/aoa-evals-mcp/scripts/validate_evals_mcp.py
python -m pytest mcp/services/aoa-evals-mcp/tests -q
python mcp/services/aoa-evals-mcp/scripts/release_check.py
```

## Report

State which MCP surface changed, which `aoa-evals` contract or reader it
exposes, what validation ran, and whether runtime exposure, source mutation,
proposal approval, verdict computation, receipt publication, or proof authority
changed.
