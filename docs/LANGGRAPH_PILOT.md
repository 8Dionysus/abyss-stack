# LANGGRAPH PILOT

## Purpose

This document defines the bounded LangGraph sidecar pilot for `abyss-stack`.

It is not a new service and not a migration of `aoa-local-ai-trials`.
It is a comparison layer for one W4-shaped supervised edit flow.

## Current pilot

Program id:
- `langgraph-sidecar-pilot-v1`
- `langgraph-sidecar-llamacpp-v1` for the disposable backend-promotion fixture gate

Current runtime path:
- `intel-full -> langchain-api /run -> ollama-native`

Current cases:
- `8dionysus-profile-routing-clarity`
- `aoa-routing-generated-surface-refresh`
- `fixture-docs-wording-alignment` only when the program id is `langgraph-sidecar-llamacpp-v1`

The docs case is also used for the explicit pause/resume scenario.

## Operator surface

Install the pilot dependency manifest before use:

```bash
python3 -m pip install --user -r scripts/requirements-langgraph-pilot.txt
```

Use:

```bash
scripts/aoa-langgraph-pilot materialize
scripts/aoa-langgraph-pilot run-case 8dionysus-profile-routing-clarity --until approval
scripts/aoa-langgraph-pilot resume-case 8dionysus-profile-routing-clarity
scripts/aoa-langgraph-pilot run-case aoa-routing-generated-surface-refresh --until done
scripts/aoa-langgraph-pilot status 8dionysus-profile-routing-clarity
```

Alternate backend/program roots are supported:

```bash
scripts/aoa-langgraph-pilot --url http://127.0.0.1:5403/run --program-id langgraph-sidecar-llamacpp-v1 run-case fixture-docs-wording-alignment --until approval
scripts/aoa-langgraph-pilot --url http://127.0.0.1:5403/run --program-id langgraph-sidecar-llamacpp-v1 resume-case fixture-docs-wording-alignment
```

## Boundaries

The sidecar pilot:
- reuses the W4 bounded-mutation contract
- reuses `approval.status.json`
- reuses the existing worktree-first landing safety posture
- keeps runtime truth local under `Logs/local-ai-trials/`
- mirrors only Markdown summaries to `Dionysus`

The sidecar pilot does not:
- add a new HTTP API
- replace `aoa-local-ai-trials`
- replace `langchain-api /run`
- widen W4 into autonomous long-horizon execution

## Artifacts

Runtime truth:
- `${AOA_STACK_ROOT}/Logs/local-ai-trials/langgraph-sidecar-pilot-v1/`
- `${AOA_STACK_ROOT}/Logs/local-ai-trials/langgraph-sidecar-llamacpp-v1/` for the disposable promotion fixture

Mirror:
- `/srv/Dionysus/reports/local-ai-trials/langgraph-sidecar-pilot-v1/`
- `/srv/Dionysus/reports/local-ai-trials/langgraph-sidecar-llamacpp-v1/` for the disposable promotion fixture

Per-case packets keep the existing local-trial packet shape:
- `case.spec.json`
- `run.manifest.json`
- `result.summary.json`
- `report.md`

The sidecar adds:
- `graph.state.json`
- `graph.history.jsonl`
- `interrupt.json`
- `approval.status.json`
- `node-artifacts/`

## Comparison goal

The sidecar should answer a narrow question:

- does LangGraph improve pause/resume and recovery clarity for a bounded supervised edit flow
- without reducing W4 safety, scope discipline, or reportability

Until that answer is positive, the existing runner remains the execution baseline.
