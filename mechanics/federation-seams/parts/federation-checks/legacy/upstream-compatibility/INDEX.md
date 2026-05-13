# Upstream Compatibility Legacy Index

Detailed compatibility inventory for the active bridge at
[`../../docs/UPSTREAM_COMPATIBILITY.md`](../../docs/UPSTREAM_COMPATIBILITY.md).

These names are not active `abyss-stack` topology. They are preserved because
stronger owner repositories or historical runtime evidence still publish or
expect them.

| Clean local route | Upstream path or ID | Owner repo | Compatibility reason | Removal trigger |
|---|---|---|---|---|
| `memo-recall-rerun` | `runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json`, `phase-alpha-memo-recall-rerun-v1` | `aoa-evals` | mirrored example and selection ID are upstream-published contract names | `aoa-evals` publishes a clean replacement and route-api compatibility traffic is retired |
| `memo-contradiction-gap` | `runtime_evidence_selection.phase-alpha-memo-contradiction-gap.example.json`, `phase-alpha-memo-contradiction-gap-v1` | `aoa-evals` | mirrored example and selection ID are upstream-published contract names | `aoa-evals` publishes a clean replacement and route-api compatibility traffic is retired |
| `memo-contradiction-rerun` | `runtime_evidence_selection.phase-alpha-memo-contradiction-rerun.example.json`, `phase-alpha-memo-contradiction-rerun-v1` | `aoa-evals` | mirrored example and selection ID are upstream-published contract names | `aoa-evals` publishes a clean replacement and route-api compatibility traffic is retired |
| `memo-contradiction-sidecar` | memo object IDs prefixed `memo.*.2026-04-03.phase-alpha-*`; fallback runtime logs under `Logs/phase-alpha/` | `aoa-memo` and historical runtime evidence | generated memo object IDs and older runtime evidence paths were published before the clean sidecar route | `aoa-memo` publishes clean object IDs and deployed runtime evidence moves to `Logs/memo-contradiction-rerun/` everywhere |
| `a2a-return-closeout` | `a2a_wave5_closeout_request`, `A2A_WAVE5_CODEX_RETURN_CHECKPOINT.md` | `aoa-sdk` | reviewed closeout request kind and SDK docs are upstream wire-contract names | `aoa-sdk` publishes a clean reviewed closeout request kind and compatibility fixtures are retired |
| `/playbooks/automation-plans` | `aoa-playbooks/generated/playbook_automation_seeds.json` | `aoa-playbooks` | upstream generated surface still uses its old file name while local route-api returns `plans` | `aoa-playbooks` publishes `playbook_automation_plans.json` and mirrored configs migrate |
| `/playbooks/automation-plan` | `/playbooks/automation-seeds`, `/playbooks/automation-seed` | route-api compatibility bridge for `aoa-playbooks` consumers | old callers may still use the previous endpoint names; responses must report `compatibility_bridge_for` | runtime callers stop using the compatibility endpoints |
| `rpg-runtime-projection` | `Dionysus/seed_staging/rpg/seed_rpg_runtime_projection_pack.md` | `Dionysus` | `Dionysus` currently owns seed garden and prep-pack staging; `abyss-stack` only points to it as an owner handoff route | Dionysus plants the prep pack into a stronger owner route or publishes a clean non-seed handoff path |

## Retirement Procedure

1. Confirm the stronger owner published the clean replacement.
2. Update source config, route-api, adapters, tests, and layout checks in one
   reviewed pass.
3. Remove or downgrade the legacy row only after the bridge no longer needs the
   upstream value.
4. Run `python scripts/validate_stack.py` and the focused package tests.
