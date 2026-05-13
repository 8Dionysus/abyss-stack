# AGENTS.md

Local guidance for `.agents/` in `abyss-stack`. Read the root `AGENTS.md`
first.

## Scope

This directory owns repo-local agent install and overlay surfaces that need to
ship with the `abyss-stack` source checkout.

## Read Before Editing

1. `.agents/README.md`
2. `.agents/skills/AGENTS.md`
3. `.agents/spark/AGENTS.md` when editing the Spark fast-loop lane
4. `mechanics/README.md`
5. `docs/MECHANICS.md`
6. `scripts/validate_nested_agents.py`

## Directory Contract

- Keep canonical skill law in the owning skill repository.
- Keep local overlays thin, portable, and explicit about the canonical upstream.
- Keep agent model lanes under `.agents/<lane>/`, not as top-level runtime
  districts.
- Do not commit private agent state, session transcripts, cache payloads, or
  generated runtime captures here.
- Route local overlay references to current package-local mechanics paths.

## Verify

```bash
python scripts/validate_nested_agents.py
python scripts/validate_stack.py
```
