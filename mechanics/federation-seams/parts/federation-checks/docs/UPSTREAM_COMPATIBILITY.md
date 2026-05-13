# Upstream Compatibility

`abyss-stack` exposes clean runtime aliases while preserving a few upstream
contract names from sibling mirrors. These names are compatibility facts, not
active local topology.

## Verdict Table

| Local active route | Upstream path or ID | Owner repo | Compatibility reason | Removal trigger |
|---|---|---|---|---|
| `memo-recall-rerun` | `runtime_evidence_selection.phase-alpha-memo-recall-rerun.example.json`, `phase-alpha-memo-recall-rerun-v1` | `aoa-evals` | mirrored example and selection ID are upstream-published contract names | `aoa-evals` publishes a clean replacement and route-api compatibility traffic is retired |
| `memo-contradiction-gap` | `runtime_evidence_selection.phase-alpha-memo-contradiction-gap.example.json`, `phase-alpha-memo-contradiction-gap-v1` | `aoa-evals` | mirrored example and selection ID are upstream-published contract names | `aoa-evals` publishes a clean replacement and route-api compatibility traffic is retired |
| `memo-contradiction-rerun` | `runtime_evidence_selection.phase-alpha-memo-contradiction-rerun.example.json`, `phase-alpha-memo-contradiction-rerun-v1` | `aoa-evals` | mirrored example and selection ID are upstream-published contract names | `aoa-evals` publishes a clean replacement and route-api compatibility traffic is retired |
| `/playbooks/automation-plans` | `aoa-playbooks/generated/playbook_automation_seeds.json` | `aoa-playbooks` | upstream generated surface still uses its old file name while local route-api returns `plans` | `aoa-playbooks` publishes `playbook_automation_plans.json` and mirrored configs migrate |
| `/playbooks/automation-plan` | `/playbooks/automation-seeds`, `/playbooks/automation-seed` | route-api compatibility bridge for `aoa-playbooks` consumers | old callers may still use the previous endpoint names; responses must report `compatibility_alias_for` | runtime callers stop using the compatibility endpoints |

## Local Rule

- Active docs use the local clean names.
- Route-api may keep compatibility aliases at the boundary.
- Tests may name upstream IDs when they prove compatibility behavior.
- Config allowlists may name upstream files only when the owning sibling still
  publishes those names.
- New local docs must add old names here first, then explain why the owner repo
  has not moved yet.
