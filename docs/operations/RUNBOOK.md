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
13. inspect eval export candidates under `${AOA_STACK_ROOT}/Logs/eval-exports/` and A2A return dry-run candidates under `${AOA_STACK_ROOT}/Logs/a2a-return-closeouts/` when runtime evidence selections, artifact hooks, or reviewed child-return closeouts may need bounded export toward `aoa-evals`
14. inspect `route-api` playbook advisory surfaces when activation, failure posture, or composition seams may explain the current route
15. inspect governed-run `artifacts/review_packet_manifest.json` and `artifacts/review_packet_audit.json` when a bounded mutation run should have produced memo or eval review candidates
16. inspect `route-api` KAG and `Tree-of-Sophia` handoff advisory surfaces when retrieval, regrounding, or source-authority seams may explain the current route
17. inspect `POST /run/federated` plus its `advisory_trace` when the live runtime may be consuming playbook or memo seams incorrectly
18. decide whether to fix forward or roll back
19. inspect the latest return events under `${AOA_STACK_ROOT}/Logs/returns/` when the route appears to be looping, widening context, or silently re-entering
20. inspect `${AOA_STACK_ROOT}/Logs/rpg/latest/` and `${AOA_STACK_ROOT}/Logs/rpg/records/` when the body-facing RPG transport looks stale, uncited, or out of parity with committed `mechanics/federation-seams/parts/rpg-runtime/generated/`
21. inspect `${AOA_STACK_ROOT}/Logs/runtime-gateway/cache-status/latest/` when a local `runtime_gateway_cache_status` artifact exists and the question is dedup, inflight replay, or `no-cache` bypass posture
22. inspect `${AOA_STACK_ROOT}/Logs/runtime-usage/latest/` when a local `runtime_usage_snapshot` exists and the question is degrade posture, strict stop, or reset-window pressure

## Useful commands

```bash
aoa-doctor
aoa-doctor --preset agent-full
aoa-check-layout
aoa-host-facts --mode public
aoa-machine-fit --mode private --write "${AOA_STACK_ROOT}/Logs/machine-fit/latest/latest.private.json"
aoa-platform-adaptation --mode private --title "Short seam title" --summary "One bounded summary" --issue-class performance
aoa-diagnose --preset intel-full --truth-goal live_available
aoa-diagnose --preset intel-full --truth-goal live_available --write-latest
aoa-diagnose --preset intel-full --truth-goal live_available --write-latest --write-last-good-ref
aoa-diagnose --preset intel-full --with-reviewed-diagnosis-ref /tmp/reviewed-diagnosis.packet.json --write-latest
aoa-export-memo-candidate --runtime-surface checkpoint_export --input-file /tmp/checkpoint-export.json --write
aoa-export-runtime-evidence-selection --input-file /tmp/runtime-evidence-selection.json --write
aoa-export-artifact-hook-candidate --input-file /tmp/artifact-hook.json --write
aoa-a2a-return-closeout-dry-run --input-file /tmp/reviewed-closeout-request.json --write
scripts/aoa-rpg-runtime-projection --check
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

aoa-run-memo-contradiction-integrity \
  --memo-root "${AOA_STACK_ROOT}/Knowledge/federation/aoa-memo" \
  --evals-root "${AOA_STACK_ROOT}/Knowledge/federation/aoa-evals"

aoa-export-artifact-hook-candidate \
  --input-file /tmp/artifact-hook.json \
  --write

aoa-a2a-return-closeout-dry-run \
  --input-file /tmp/reviewed-closeout-request.json \
  --write
```

For filesystem-first RPG runtime projection refresh and parity check:

```bash
scripts/aoa-rpg-runtime-projection
scripts/aoa-rpg-runtime-projection --check
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
curl -X POST http://127.0.0.1:5403/run/federated \
  -H 'content-type: application/json' \
  -d '{"user_text":"Summarize the current route","playbook_id":"AOA-P-0008"}'

curl -X POST http://127.0.0.1:5403/run/federated \
  -H 'content-type: application/json' \
  -d '{"user_text":"Use this memo card if it helps","memo":{"family":"router","mode":"semantic","id":"AOA-M-0001"}}'

curl -X POST http://127.0.0.1:5403/run/federated \
  -H 'content-type: application/json' \
  -d '{"user_text":"Use the Zarathustra retrieval surface as advisory context only","kag":{"inspect_id":"AOA-K-0011"}}'

curl -X POST http://127.0.0.1:5403/run/federated \
  -H 'content-type: application/json' \
  -d '{"user_text":"Stay source-first and use a local search retrieval hint only if it helps","kag":{"query_mode":"local_search"}}'
```

Expect `503` when `AOA_FEDERATED_RUN_ENABLED` is off or `route-api` is not currently reachable.
Expect `409` when a playbook filter matches more than one playbook and the runtime refuses to guess.
Expect the normal answer plus a redacted `advisory_trace`; this path still does
not promote `aoa-kag`, `aoa-memo`, `aoa-playbooks`, `aoa-routing`, or mirrored
`tos-source` surfaces into runtime authority.

For a named opt-in startup bundle around this seam:

```bash
aoa-preset-profiles --preset agent-federation --paths
aoa-profile-endpoints --preset agent-federation
aoa-federated-check
aoa-federated-check --require-enabled
aoa-federated-check --require-enabled --playbook-id AOA-P-0008
aoa-federated-check --require-enabled --inspect-id AOA-K-0011
aoa-federated-check --require-enabled --memo-id AOA-M-0001
```

For planned gateway cache-status inspection when the artifact exists locally:

```bash
jq . "${AOA_STACK_ROOT}/Logs/runtime-gateway/cache-status/latest/gateway-local.json"
```

Read `hit_state`, `inflight_state`, and `recent_decisions` there.
Its absence is not a failure because the contract lands before live cache activation.

For planned runtime usage snapshot inspection when the artifact exists locally:

```bash
jq . "${AOA_STACK_ROOT}/Logs/runtime-usage/latest/workhorse-local.snapshot.json"
```

Read `policy_mode`, `degrade_state`, `strict_stop`, `baseline_cost_estimate`, `savings_estimate`, and `reset_at` there.
Its absence is not a failure because the contract lands before live aggregation.

For planned diagnostic spine inspection when the artifact exists locally:

```bash
jq . <(scripts/aoa-diagnose --preset intel-full --truth-goal live_available)
jq . "${AOA_STACK_ROOT}/Logs/diagnostics/latest/diagnostic_target.json"
jq . "${AOA_STACK_ROOT}/Logs/diagnostics/latest/diagnostic_session.json"
jq . "${AOA_STACK_ROOT}/Logs/diagnostics/latest/diagnosis_companion.json"
jq . "${AOA_STACK_ROOT}/Logs/diagnostics/latest/repair_handoff.json"
jq . "${AOA_STACK_ROOT}/Logs/diagnostics/latest/last_good.ref.json"
```

Read `target`, `axes`, `truth_status`, `drifts`, `exit_class`, and `next_moves` there.
Treat that file as the runtime copy of `diagnostic_session_v1`.
`aoa-diagnose --write-latest` also refreshes `diagnostic_target.json`,
`diagnostic_session.json`, `diagnosis_companion.json`,
`repair_handoff.json`, and the corresponding record copy under
`Logs/diagnostics/records/`.
Use `--write-last-good-ref` only when you want to promote the current green
pass into `last_good.ref.json` explicitly.
Use `--write-reviewed-diagnosis-ref` when you want the runtime seam to record
an explicit review bridge over the current `diagnosis_companion.json`.
That is the mode that writes `reviewed_diagnosis.ref.json`.
Use `--with-reviewed-diagnosis-ref` when a reviewed diagnosis packet already
exists and the repair handoff should stop blocking on that prerequisite.

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
