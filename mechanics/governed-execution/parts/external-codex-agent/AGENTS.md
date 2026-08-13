# AGENTS.md

## Applies to

This card applies to `mechanics/governed-execution/parts/external-codex-agent/`.

## Role

This part owns the runtime transport and receipts for one exact external Codex
incarnation running as a separate operating-system process. It does not own
model fit, role meaning, eval verdicts, repository acceptance, or landing
authority.

## Read before editing

Read the repository, `mechanics/`, and `mechanics/governed-execution/` route
cards, then this part's `README.md`, `CONTRACT.md`, `DIRECTION.md`,
`PROVENANCE.md`, `SUSPENSION.md`, and `VALIDATION.md`.

## Boundaries

- Keep built-in Codex multi-agent transport disabled.
- Bind model, effort, role, task, workspace, tools, permissions, observe-only usage metering,
  continuation, and wake policy through exact owner-qualified artifacts.
- Treat runtime completion as transport evidence, never model-fit proof or
  owner acceptance.
- Fail closed on workspace-byte drift, unknown command observation, identity
  drift, out-of-scope paths, forbidden effects, or ambiguous authority.
- Preserve exact threads, events, failed attempts, and immutable study inputs;
  do not rewrite prior trial evidence.
- Treat a waiting parent as durable state outside inference. Re-enter only from
  an exact runtime-admitted child event; never keep Sol alive to poll or use a
  failed/non-significant event as a wake substitute.
- Do not enable commit, push, PR, merge, release, publication, service, secret,
  global-config, or general network effects in the first owner contour. An
  exact role profile may expose only its named loopback AoA MCP; that transport
  does not grant the model shell network or access to other MCP servers.

## Validation

Run:

```bash
AOA_SDK_SOURCE_ROOT=/absolute/path/to/aoa-sdk \
AOA_AGENTS_SOURCE_ROOT=/absolute/path/to/aoa-agents \
AOA_SKILLS_SOURCE_ROOT=/absolute/path/to/aoa-skills \
PYTHONPATH=/absolute/path/to/aoa-sdk/src \
python -m pytest -q \
  mechanics/governed-execution/parts/external-codex-agent/tests
python -m py_compile \
  scripts/aoa-external-codex-agent \
  scripts/aoa-external-actor-bind \
  mechanics/governed-execution/parts/external-codex-agent/bind_external_actor_launch.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_nested_evidence.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_projection.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_mount_launcher.py \
  mechanics/governed-execution/parts/external-codex-agent/external_codex_supervisor.py \
  mechanics/governed-execution/parts/external-codex-agent/install_external_codex_runtime.py \
  mechanics/governed-execution/parts/external-codex-agent/prepare_landing_study.py
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```

Real-model trials are separate evidence runs. Do not substitute them for the
focused deterministic suite or start them implicitly during validation.

## Closeout

Report exact source changes, deterministic checks, real-process evidence kept
or skipped, residual authority or portability gaps, and the next owner route.
State explicitly that no external effect or model-fit verdict was claimed.
