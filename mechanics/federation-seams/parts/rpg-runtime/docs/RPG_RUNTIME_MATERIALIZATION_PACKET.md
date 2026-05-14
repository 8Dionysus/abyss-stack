# RPG Runtime Materialization Packet

## Role

This packet closes the filesystem-first RPG runtime materialization obligation.
It proves that source-generated RPG runtime collections can be copied into
runtime `latest/` and `records/` layouts without widening route authority.

It is not a live `/rpg/*` endpoint, a reward engine, an unlock writer, or a
source quest mutation path.

## Packet Surface

Run from the source checkout against a synthetic or operator-selected runtime
root:

```bash
AOA_STACK_ROOT=/tmp/<runtime> scripts/aoa-install-layout
scripts/aoa-rpg-runtime-projection --generated-only --check
scripts/aoa-rpg-runtime-projection --stack-root /tmp/<runtime>
scripts/aoa-rpg-runtime-projection --stack-root /tmp/<runtime> --check
```

The materialized runtime files are:

- `Logs/rpg/latest/agent_build_snapshots.json`
- `Logs/rpg/latest/frontend_projection_bundles.json`
- `Logs/rpg/latest/quest_run_results.json`
- `Logs/rpg/latest/reputation_ledgers.json`
- `Logs/rpg/records/agent_build_snapshots/<timestamp>.json`
- `Logs/rpg/records/frontend_projection_bundles/<timestamp>.json`
- `Logs/rpg/records/quest_run_results/<timestamp>.json`
- `Logs/rpg/records/reputation_ledgers/<timestamp>.json`

## 2026-05-13 Verdict

The packet materialized all four source-generated collections into synthetic
runtime `latest/` files and timestamped `records/` files, then passed projection
parity. This closes the `abyss-stack` runtime materialization quest for the
source route.

Future work may choose whether a live service consumes these files, but that is
a new runtime-loop decision. It must not be smuggled into this materialization
packet.

## Stop-Lines

- no live `/rpg/*` endpoints are added by this packet
- no quest state is written back to owner repositories
- no hidden reward, rank, or unlock authority is introduced
- sibling owner refs remain citations and compatibility handoffs, not
  `abyss-stack` doctrine

