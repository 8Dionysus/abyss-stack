# A2A Return Dry-Run

This document defines the `abyss-stack` dry-run adapter for reviewed A2A summon
child-return closeout payloads.

It does not enable live child execution.
It does not publish eval verdicts.
It does not promote memo objects.
It does not replace the `aoa-sdk` A2A control-plane helpers.

## Adapter

`scripts/aoa-a2a-return-closeout-dry-run` reads one reviewed
`a2a_wave5_closeout_request` payload and emits a private runtime-owned wrapper
artifact:

- `artifact_kind`: `aoa.runtime-a2a-return-closeout-dry-run`
- `dry_run`: `true`
- `live_automation`: `false`
- `exported_by`: `scripts/aoa-a2a-return-closeout-dry-run`

By default it writes only to stdout.
With `--write`, it writes under:

- `${AOA_STACK_ROOT}/Logs/a2a-return-closeouts/latest/`
- `${AOA_STACK_ROOT}/Logs/a2a-return-closeouts/records/`

## Inputs

The adapter expects the SDK-shaped reviewed closeout request:

- `request_kind`: `a2a_wave5_closeout_request`
- `reviewed`: `true`
- `closeout_id`
- `a2a_child`
- `return_plan`
- `checkpoint_bridge_plan`

The source contract lives in `aoa-sdk`, not in this repository.

The adapter may also accept the full SDK E2E fixture at
`/srv/AbyssOS/aoa-sdk/examples/a2a/summon_return_checkpoint_e2e.fixture.json`; in that
case it reads the nested `reviewed_closeout_request` and still emits only the
same private dry-run wrapper.

## Output Boundary

The output is a runtime receipt candidate.

It may assemble:

- a dry-run `runtime_receipt_candidate`
- bounded memo export candidate hints
- the A2A artifact-to-verdict hook template ref
- owner-source contract refs for later review

It must not claim:

- live child execution
- live closeout publication
- eval verdict completion
- memo canon promotion
- SDK authority transfer into `abyss-stack`

## Example

```bash
scripts/aoa-a2a-return-closeout-dry-run \
  --input-file /srv/AbyssOS/aoa-sdk/examples/a2a/reviewed_closeout_request.example.json
```

The full-fixture form is also accepted:

```bash
scripts/aoa-a2a-return-closeout-dry-run \
  --input-file /srv/AbyssOS/aoa-sdk/examples/a2a/summon_return_checkpoint_e2e.fixture.json
```

Use `--write` only when a private runtime-local candidate file is wanted.

## Owner Refs

- `repo:aoa-sdk/docs/A2A_WAVE5_CODEX_RETURN_CHECKPOINT.md`
- `repo:aoa-sdk/examples/a2a/summon_return_checkpoint_e2e.fixture.json`
- `repo:aoa-playbooks/playbooks/a2a-summon-return-checkpoint/PLAYBOOK.md`
- `repo:aoa-evals/examples/artifact_to_verdict_hook.a2a-summon-return-checkpoint.example.json`
- `repo:aoa-memo/docs/A2A_CHILD_RETURN_WRITEBACK.md`
