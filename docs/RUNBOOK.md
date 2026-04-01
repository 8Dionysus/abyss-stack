# RUNBOOK

## Quick triage

When something feels wrong, use this order:

1. check profile and module intent
2. check host-readiness and runtime layout
3. check expected profile endpoints and profile composition
4. check internal-only probes when relevant
5. check rendered runtime truth when composition may be the problem
6. capture or compare host facts when the machine itself may have drifted
7. refresh or compare machine-fit when the question is what this host should currently prefer
8. capture a bounded platform-adaptation record when the seam looks machine-specific or likely to recur on another platform
9. check container state
10. check health endpoints
11. check logs
12. inspect memo export candidates under `${AOA_STACK_ROOT}/Logs/memo-exports/` when recurrence, checkpoint, or review artifacts may need bounded export toward `aoa-memo`
13. inspect eval export candidates under `${AOA_STACK_ROOT}/Logs/eval-exports/` when runtime evidence selections or artifact hooks may need bounded export toward `aoa-evals`
14. inspect `route-api` playbook advisory surfaces when activation, failure posture, or composition seams may explain the current route
15. inspect governed-run `artifacts/review_packet_manifest.json` and `artifacts/review_packet_audit.json` when a bounded mutation run should have produced memo or eval review candidates
16. inspect `route-api` KAG and `Tree-of-Sophia` handoff advisory surfaces when retrieval, regrounding, or source-authority seams may explain the current route
17. inspect `POST /run/federated` plus its `advisory_trace` when the live runtime may be consuming playbook or memo seams incorrectly
18. decide whether to fix forward or roll back
19. inspect the latest return events under `${AOA_STACK_ROOT}/Logs/returns/` when the route appears to be looping, widening context, or silently re-entering

## Useful commands

```bash
aoa-doctor
aoa-doctor --preset agent-full
aoa-check-layout
aoa-host-facts --mode public
aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
aoa-platform-adaptation --mode private --title "Short seam title" --summary "One bounded summary" --issue-class performance
aoa-export-memo-candidate --runtime-surface checkpoint_export --input-file /tmp/checkpoint-export.json --write
aoa-export-runtime-evidence-selection --input-file /tmp/runtime-evidence-selection.json --write
aoa-export-artifact-hook-candidate --input-file /tmp/artifact-hook.json --write
scripts/aoa-governed-run audit <run-id>
scripts/aoa-governed-run replay-review-packets <run-id>
curl http://127.0.0.1:5402/playbooks/activation
curl http://127.0.0.1:5402/kag/registry
aoa-preset-profiles --preset agent-full --paths
aoa-profile-modules --profile core
aoa-profile-endpoints --profile core
aoa-render-services --profile core
aoa-internal-probes --preset agent-full
aoa-status --profile core
aoa-smoke --with-internal --preset agent-full
aoa-logs --profile core
```

For rendered config output:

```bash
aoa-render-config --preset agent-full --write /tmp/abyss.rendered.yml
```

Treat rendered output as potentially secret-bearing.

For private host-facts capture during local incident work:

```bash
aoa-host-facts --mode private --write "${AOA_STACK_ROOT}/Logs/host-facts/incident.private.json"
```

For a bounded platform-adaptation record when the issue is likely to recur:

```bash
aoa-platform-adaptation \
  --mode private \
  --title "Short seam title" \
  --summary "One bounded summary" \
  --issue-class performance \
  --write "${AOA_STACK_ROOT}/Logs/platform-adaptations/latest/latest.private.json"
```

For a bounded runtime memo export candidate:

```bash
aoa-export-memo-candidate \
  --runtime-surface checkpoint_export \
  --input-file /tmp/checkpoint-export.json \
  --write
```

For bounded runtime eval export candidates:

```bash
aoa-export-runtime-evidence-selection \
  --input-file /tmp/runtime-evidence-selection.json \
  --write

aoa-export-artifact-hook-candidate \
  --input-file /tmp/artifact-hook.json \
  --write
```

For governed-run review-packet audit and replay from stored context only:

```bash
scripts/aoa-governed-run audit <run-id>
scripts/aoa-governed-run replay-review-packets <run-id>
scripts/aoa-governed-run status <run-id> --explain
```

For playbook advisory inspection through the localhost federation seam:

```bash
curl http://127.0.0.1:5402/playbooks/activation
curl http://127.0.0.1:5402/playbooks/federation
curl -X POST http://127.0.0.1:5402/playbooks/select \
  -H 'content-type: application/json' \
  -d '{"scenario":"bounded_change_safe"}'
```

For the live federated run path through `langchain-api`:

```bash
curl -X POST http://127.0.0.1:5401/run/federated \
  -H 'content-type: application/json' \
  -d '{"user_text":"Summarize the current route","playbook_id":"AOA-P-0008"}'

curl -X POST http://127.0.0.1:5401/run/federated \
  -H 'content-type: application/json' \
  -d '{"user_text":"Use this memo card if it helps","memo":{"family":"router","mode":"semantic","id":"claim-1"}}'
```

Expect `503` when `AOA_FEDERATED_RUN_ENABLED` is off or `route-api` is not currently reachable.
Expect `409` when a playbook filter matches more than one playbook and the runtime refuses to guess.

For KAG and `Tree-of-Sophia` handoff inspection through the localhost federation seam:

```bash
curl http://127.0.0.1:5402/kag/registry
curl http://127.0.0.1:5402/kag/tos-export
curl -X POST http://127.0.0.1:5402/kag/query-mode \
  -H 'content-type: application/json' \
  -d '{"mode":"global_search"}'
```

For combined surfaces:

```bash
aoa-preset-profiles --preset intel-full --paths
aoa-profile-endpoints --preset intel-full
aoa-smoke --with-internal --preset intel-full
```

Low-level checks:

```bash
systemctl --user status podman-compose-abyss --no-pager
podman ps -a --no-trunc
ss -lntp
```

## Internal-only services

These should not expose host ports:
- `docs-api`
- `aoa-browser`
- `cadvisor`

If they accidentally appear on host ports, treat that as drift.

## First rollback instinct

If a change widened scope, broke locality, tangled profiles, mixed Windows host paths with Linux runtime paths, or introduced unreviewed host-facts exposure, prefer a small rollback over improvising a giant repair.
