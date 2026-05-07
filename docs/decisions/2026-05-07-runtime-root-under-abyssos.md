# 2026-05-07 Runtime Root Under AbyssOS

Status: Accepted

## Context

After the workspace relocation, the live runtime tree and source-authored defaults had drifted. The deployed tree was already under the AbyssOS workspace, while source docs, compose defaults, helper scripts, examples, and the user systemd unit still carried the former standalone stack-root assumption.

That drift made path reasoning flatter than the project topology: `abyss-stack` is the runtime owner, but it now belongs inside the broader AbyssOS workspace route.

## Decision

Use `/srv/AbyssOS/abyss-stack` as the canonical deployed runtime root.

Keep the source checkout separate at `~/src/abyss-stack` by default, or `${AOA_SOURCE_ROOT}` when intentionally relocated. Runtime helpers should continue to bridge source-authored changes into `${AOA_CONFIGS_ROOT}` instead of treating the deployed tree as the source repository.

## Alternatives

- Keep the former standalone deployed root and add compatibility glue from the AbyssOS workspace.
- Treat the live deployed tree as the editable source.
- Move the canonical deployed runtime root under `/srv/AbyssOS/abyss-stack` and make the old standalone root a stale path.

## Rationale

The selected path makes the topology explicit. The runtime remains owned by `abyss-stack`, but its deployed location is visibly inside the AbyssOS workspace that coordinates AoA, ToS, and runtime surfaces.

It also removes a post-relocation tail that could break user units, parity checks, docs, and future machine integration. The source/live distinction remains intact: source changes are not live until the deployment bridge syncs them into the deployed `Configs` tree.

## Consequences

- `AOA_STACK_ROOT` defaults to `/srv/AbyssOS/abyss-stack`.
- `AOA_CONFIGS_ROOT` defaults to `/srv/AbyssOS/abyss-stack/Configs`.
- Compose modules, docs, examples, scripts, and validators should not reintroduce the former standalone deployed root.
- Existing user systemd links may need to be refreshed so they point at the deployed unit under the AbyssOS workspace.
- This decision does not make `abyss-machine` part of `abyss-stack`; machine integration should stay a later read-only bridge unless explicitly redesigned.

