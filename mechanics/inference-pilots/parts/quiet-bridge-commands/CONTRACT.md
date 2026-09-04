# Quiet Bridge Operator Contract

The stable wrappers `scripts/aoa-long-horizon-pilot` and
`scripts/aoa-bounded-autonomy-pilot` route to this part's active runners.
They preserve bounded compatibility behavior; historical pilot wave notes
are not execution backends or current deployment evidence.

## Operator surface

Both wrappers expose `materialize`,
`run-scenario <scenario-id> --until milestone|done`,
`resume-scenario <scenario-id>`, `status --all`, and `status <scenario-id>`.
For example, `scripts/aoa-long-horizon-pilot materialize` and
`scripts/aoa-bounded-autonomy-pilot materialize` create the respective planned
scenario surfaces; they do not prove a scenario passed.

The preserved default runner endpoint is `http://127.0.0.1:5403/run`.
Program IDs, scenario definitions, allowed files, and endpoint overrides are
owned by the active runners in `runners/`; they are not copied into another
historical catalog here. `implementation_patch` remains bounded by each
scenario's declared mutation policy.

## Approval and mutation boundary

Long-horizon mutation scenarios retain `plan_freeze`, `first_mutation`, and
`landing` gates. Bounded-autonomy mutation scenarios retain `plan_freeze` and
`landing`; they do not silently inherit a third gate from the other runner.
Read-only scenarios must remain read-only. A planned case, source reference,
or materialized packet never supplies approval on its own.

Mutation uses the runner's declared file scope and isolated worktree posture.
Repair does not broaden that scope. Landing requires explicit approval;
neither wrapper grants permission to push or create a PR.

## Evidence and authority

Keep `case.spec.json`, `run.manifest.json`, `result.summary.json`, and
`report.md` distinct from live service health. Approval, graph, worktree, and
landing artifacts retain their runner-owned contracts.

Interpret `trial_proven` and `live_available` through
[TRUTH_SURFACES.md](../../../diagnostic-spine/parts/truth-surfaces/docs/TRUTH_SURFACES.md).
Use `scripts/aoa-status --autonomy` for the operator health route. A successful
historical pilot or local source test is not proof of deployed availability.
