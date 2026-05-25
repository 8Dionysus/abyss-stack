# AGENTS.md

Local route card for `mcp/services/aoa-evals-mcp/`.

## Purpose

`aoa-evals-mcp` is the thin MCP access plane for OS Abyss bounded proof
surfaces. It lets agents select, inspect, expand, compare, and prepare
candidate evidence/report skeletons without turning MCP into proof authority.

## Owner Lane

This stack-owned MCP surface owns:

- MCP resources, tools, prompts, source discovery, CLI, smoke tests, and service
  packaging for `aoa_evals`.
- The adapter boundary between `aoa-evals` generated readers, runtime-candidate
  readers, and Codex/OS Abyss access.
- Candidate-only report skeleton and runtime evidence template helpers.

It does not own:

- eval bundle claims, verdict logic, report contracts, or proof authority;
- generated reader source truth;
- runtime evidence acceptance;
- receipt publication or bundle promotion.

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
| candidate runtime evidence posture | `aoa-evals:mechanics/audit/parts/candidate-readers/` |
| report skeleton behavior | `src/aoa_evals_mcp/core.py` and source bundle report contract |
| Codex-plane registration | `8Dionysus:config/codex_plane/runtime_manifest.v1.json` |

## AGENTS Stack Law

- MCP exposes access; it does not promote proof.
- Generated readers and MCP responses stay weaker than bundle-local `EVAL.md`
  and `eval.yaml`.
- Runtime evidence templates stay candidate-only until bundle-local review.
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
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli inspect aoa-bounded-change-quality
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli expand aoa-bounded-change-quality --section-key intent
PYTHONPATH=mcp/services/aoa-evals-mcp/src python -m aoa_evals_mcp.cli runtime-evidence-template aoa-bounded-change-quality
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
verdict computation, receipt publication, or proof authority changed.
