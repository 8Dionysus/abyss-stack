# Upstream Compatibility Bridge

This is the single active bridge for upstream compatibility names in
`abyss-stack` federation seams.

Active runtime surfaces should use clean local names and route old or
owner-published names through this bridge. Detailed upstream identifiers,
lineage notes, and removal triggers live in
[`../legacy/upstream-compatibility/INDEX.md`](../legacy/upstream-compatibility/INDEX.md).

## Active Bridge

| Clean local route | Stronger owner | Active handling |
|---|---|---|
| `memo-recall-rerun` | `aoa-evals` | consume mirrored eval template through the clean local route |
| `memo-contradiction-gap` | `aoa-evals` | consume mirrored eval template through the clean local route |
| `memo-contradiction-rerun` | `aoa-evals` and `aoa-memo` | consume mirrored eval and memo evidence through the clean sidecar route |
| `a2a-return-closeout` | `aoa-sdk` | accept reviewed SDK wire input and emit a clean runtime family |
| `automation-plans` | `aoa-playbooks` | expose clean route-api plan language while reading the upstream generated surface |
| `rpg-runtime-projection` | `Dionysus` | keep seed-garden prep-pack references as owner handoff refs only |

## Rule

- Active docs link here, not to the detailed legacy inventory.
- Runtime adapters may accept upstream contract values only at explicit bridge
  boundaries.
- Tests may assert upstream values only when proving the bridge.
- Removal starts from the legacy index after the stronger owner publishes a
  clean replacement.
