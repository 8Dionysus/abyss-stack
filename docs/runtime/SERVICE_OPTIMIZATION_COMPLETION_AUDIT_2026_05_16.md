# Service Optimization Completion Audit - 2026-05-16

This audit maps the operator objective to concrete artifacts and current
evidence. The live apply gate has completed: selected services now have their
staged cgroup limits applied, and the hard completion audit passes.

## Objective Restatement

Deliver a source-backed, machine-aware optimization path for the services shown
in the abyss-stack service view:

- fix the technical debt that made host-local overlay selection manual
- classify which services should be resident, explicit, optional, or lab-only
- use current upstream and field research to tune selected services
- prepare the first source-linked RAG, Agentic-RAG, and DAG manifest path inside
  `abyss-stack` without adding avoidable always-on resident services
- stage the selected resource guards through abyss-stack source truth and the
  deployed `Configs` mirror
- verify the difference between staged configuration and live containers
- apply the guards only in a safe machine window

## Prompt To Artifact Checklist

| Requirement | Evidence | Status |
|---|---|---|
| Fix technical debt first | `scripts/aoa-install-systemd` now supports `--overlay` via `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`; it writes `AOA_EXTRA_COMPOSE_FILES` into `20-runtime-selection.conf` | done |
| Keep source/deployed boundary explicit | `scripts/aoa-sync-configs --delete` completed; `python3 scripts/validate_stack.py --parity-check` passed | done |
| Study current service set | `docs/runtime/SERVICE_SELECTION.md` defines tiers and runtime shapes for storage, worker, tools, observability, workflows, speech, rerank, and model lanes | done |
| Preserve the original screenshot baseline | `docs/runtime/service-inventory-2026-05-14.v1.json` records the operator screenshot service list, links it to `service-selection-policy.v1.json`, and explains `rerank-api` plus `rag-api` as current selected add-ons after the screenshot | done |
| Keep service posture machine-checkable | `docs/runtime/service-selection-policy.v1.json` maps services to posture, tier, owner profile, and resource guard; `scripts/validate_stack.py` validates required services, selected/opt-in boundaries, and current preset/profile services versus `selected_now` | done |
| Compare live containers to service posture | `scripts/aoa-status --service-selection` reports missing selected services and unexpectedly running opt-in, fallback, lab, or unknown services | done |
| Summarize apply readiness | `scripts/aoa-status --optimization` combines service selection, resource guards, game guard, and resource-plan readiness into one apply/no-apply verdict | done |
| Keep objective completion machine-auditable | `scripts/aoa-status --optimization-audit` maps prompt requirements to concrete source and live evidence before any completion claim | done |
| Keep completion gate executable | `scripts/aoa-status --optimization-audit --require-complete` exits non-zero until all required checks are `done` | done |
| Use web/upstream/forum research | `docs/runtime/SERVICE_OPTIMIZATION_RESEARCH_2026_05.md` records official docs and field evidence for n8n, Qdrant, Neo4j, Redis, PostgreSQL, Prometheus, cAdvisor, llama.cpp, and operator reports | done |
| Decide what is resident vs opt-in | `SERVICE_SELECTION.md` keeps storage and one text lane as working runtime, keeps n8n workflows opt-in, keeps BabelVox lab-only, keeps host TTS/dictation protected | done |
| Add needed resource guards | `compose/tuning/storage.intel-285h.resource-guard.yml`, `intel-worker.thin-host.yml`, `federation.thin-host.yml`, `observability.thin-host.yml`, `tools.thin-host.yml`, `workflows.thin-host.yml`, and `llamacpp.gemma4-e2b.intel-285h.vulkan.yml` | done |
| Add RAG orchestration without a new vector DB | `compose/modules/46-rag-api.yml`, `compose/profiles/rag.txt`, `compose/tuning/rag.thin-host.yml`, `config-templates/Configs/rag/`, and `config-templates/Services/rag-api/` define the first RAG layer over Qdrant, OVMS embeddings, `langchain-api`, lazy `rerank-api`, advisory `route-api`, and the existing Gemma lane | done |
| Keep DAG engines from becoming accidental resident load | `config-templates/Configs/rag/dag-jobs.v1.json` and `docs/decisions/ABYSS-STACK-D-0030-rag-orchestration-profile.md` keep n8n, Dagster, and Temporal as explicit future/integration lanes rather than the current always-on RAG brain | done |
| Persist current host selection | `systemctl --user show podman-compose-abyss.service -p Environment` shows `AOA_STACK_PRESET=intel-full`, `AOA_STACK_PROFILE=federation,reranking,rag`, and the staged overlay list including `compose/tuning/rag.thin-host.yml` | done |
| Keep source/deployed parity live-checkable | `scripts/aoa-status --optimization-audit` runs `python3 scripts/validate_stack.py --parity-check --deployed-configs-root /srv/AbyssOS/abyss-stack/Configs` from the source checkout | done |
| Distinguish staged vs live limits | `scripts/aoa-status --resource-guards` reported the earlier `staged_not_applied staged=7 applied=10` gap and now reports `applied` with `applied=18 staged=0` | done |
| Provide guarded apply route | `scripts/aoa-apply-resource-guards` records pre/post status and refuses to reload/recreate/restart while `abyss-machine processes game-guard --json` is active unless `--force` is passed; default `recreate` applies staged cgroup changes with temporary `AOA_UP_FORCE_RECREATE=1` | done |
| Keep guarded apply route from regressing | `scripts/validate_stack.py` requires `aoa-apply-resource-guards` to preserve dry-run, force gate, method selection, game-guard check, post-apply check, and failure behavior | done |
| Preserve pre/post resource evidence | `scripts/aoa-apply-resource-guards` writes `pre-podman-stats.txt`, `post-podman-stats.txt`, `pre-memory.txt`, and `post-memory.txt` under `Logs/resource-guards/latest/` | done |
| Preserve service selection after apply | `scripts/aoa-apply-resource-guards` writes `pre-service-selection.json` and `post-service-selection.json`, then fails if post status is not `ok` | done |
| Preserve protected host capabilities after apply | `scripts/aoa-apply-resource-guards` writes `pre-protected-units.txt` and `post-protected-units.txt`, then fails if host TTS, dictation, TTS keep-warm, or stack user unit are not active | done |
| Support supervised safe-window apply | `scripts/aoa-apply-resource-guards --wait-game-guard-clear --wait-resource-plan-clear` can wait for the game guard and host resource plan to clear, then run the default recreate apply without `--force` | done |
| Gate apply on host background pressure | `scripts/aoa-apply-resource-guards` checks `abyss-machine resource plan --class medium --kind generic --unattended --json` and records `pre-resource-plan.json` before non-forced live mutation, plus `post-resource-plan.json` after a real apply | done |
| Support shell-independent safe-window apply | `systemd/user/abyss-stack-resource-guards-apply.service` is a manual one-shot unit for the same wait/apply route; it is linked as a user unit and remains disabled/inactive until explicitly started | done |
| Avoid breaking TTS/dictation | `systemctl --user is-active abyss-tts-server.service abyss-dictation-server.service abyss-tts-keepwarm.timer podman-compose-abyss.service` returned all `active` | done |
| Verify live RAG endpoints | `scripts/aoa-smoke --profile rag` passed, including `rag-api /health`, `/sources`, and `/dag/jobs`; manual `GET /agentic-rag/graph` also returned the source-owned graph manifest | done |
| Verify live RAG indexing and retrieval | `POST /ingest/source` indexed 61 runtime docs into Qdrant as 194 chunks; Qdrant reports collection `abyss_stack_rag_chunks_v1` green with `points_count=194`; `POST /retrieve` returns RAG/profile/service-catalog citations | done |
| Verify Agentic-RAG and rerank integration | `POST /agentic-rag/run` produced a cited Gemma answer through `langchain-api`; `POST /retrieve` with `rerank=true` loaded and used `rerank-api`, then `/admin/unload?exit_process=false` returned the reranker to `loaded=false` without stopping the service | done |
| Keep this audit validation-backed | `python3 -m pytest` returned `304 passed`; `python3 scripts/validate_stack.py`, `python3 scripts/validate_stack.py --parity-check`, `python3 scripts/validate_decision_records.py`, and `python3 scripts/validate_nested_agents.py` passed after the RAG service, policy, and live apply | done |
| Apply live cgroup limits to all selected services | `/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-apply-resource-guards --method reload` completed; `aoa-status --resource-guards` reports `applied` with `applied=18 staged=0` | done |

## Completion Evidence

The staged configuration has been applied to existing containers. Current
deployed readout:

```text
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-status --resource-guards --json
summary.status = applied
summary.staged_not_applied = 0
summary.applied = 18
summary.missing_live_container = 0
```

The guarded RAG apply route completed without `--force`:

```text
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-apply-resource-guards --method reload
resource guard status after apply: applied staged=0
service selection after apply: ok
```

The live RAG path is present and has a small verified runtime-docs index:

```text
curl http://127.0.0.1:5406/health
ok = true
checks.qdrant.result.collections[0].name = abyss_stack_rag_chunks_v1
checks.langchain.embeddings_provider = ovms
checks.rerank_api.loaded = false

curl http://127.0.0.1:6333/collections/abyss_stack_rag_chunks_v1
result.status = green
result.points_count = 194
```

The aggregate deployed readiness check now gives the closed-state verdict:

```text
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-status --optimization
optimization: ok
service selection: ok
resource guards: applied
apply allowed: False
next: no resource-guard apply needed
```

The completion audit hard gate now passes:

```text
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-status --optimization-audit --require-complete
rc=0
optimization audit: complete
completion ready: True
checks: done=15 blocked=0 missing=0 failed=0 total=15
```

For scripts or handoff checks, use the hard gate:

```text
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-status --optimization-audit --require-complete
```

If the same staged/live gap reappears after future overlay changes, the guarded
route is:

```text
/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-apply-resource-guards --wait-game-guard-clear --wait-resource-plan-clear
```

## Completion Gate

This objective is complete because all of the following are true:

1. `abyss-machine processes game-guard --json` reports no active game, or the
   operator explicitly chooses `--force`.
2. `/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-apply-resource-guards` runs
   successfully with its default `recreate` method, or with an explicitly chosen
   method that still produces `summary.status = applied`.
3. `/srv/AbyssOS/abyss-stack/Configs/scripts/aoa-status --resource-guards`
   reports `applied`.
4. `post-service-selection.json` reports `ok`.
5. `post-protected-units.txt` shows host TTS, dictation, TTS keep-warm, and
   stack user unit active.
6. `post-podman-stats.txt`, `post-memory.txt`, and `post-resource-plan.json` are
   captured after apply for the tuned service set.
7. TTS, dictation, and the stack user unit remain active after apply.

The stack is no longer in a staged-but-unapplied cgroup state.
