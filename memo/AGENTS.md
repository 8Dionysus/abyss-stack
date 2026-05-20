# AGENTS.md

## Applies to

This card applies to `memo/`.

## Role

`memo/` is the abyss-stack local memory port. It holds runtime-side memory
candidates, receipts, exports, and local notes before any reviewed landing in
`aoa-memo`.

## Read before editing

1. Root `AGENTS.md`
2. `BOUNDARIES.md`
3. `mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md`
4. This `README.md`
5. `mcp/services/aoa-memo-mcp/AGENTS.md`

## Boundaries

Write locally as `write_candidate_only` unless a stronger reviewed route is
named by `aoa-memo`.

Use `PORT.yaml` for the local port contract and `INDEX.md` / `index.min.json`
as generated read models. Use `candidates/` for proposed memory, `receipts/`
for review or handoff traces, `exports/` for packets meant for `aoa-memo`, and
`local/` for stack-local notes.

## Candidate Route

Create candidates through the MCP helper from the `abyss-stack` repo root:

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli create-candidate \
  --repo abyss-stack \
  --evidence-ref mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md \
  --claim "Runtime memory access should route through reviewed local candidates."
```

Then validate the emitted candidate path:

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli validate-candidate path/to/candidate.json
```

## Validation

```bash
python mcp/services/aoa-memo-mcp/scripts/validate_memo_mcp.py
python /srv/AbyssOS/aoa-memo/scripts/memory/validate_local_memo_port.py --path memo
python /srv/AbyssOS/aoa-memo/scripts/memory/build_local_memo_port_index.py --path memo --check
python -m pytest mcp/services/aoa-memo-mcp/tests -q
```

## Closeout

Report candidate path, evidence refs, validation result, and whether the item
stayed local or was exported for reviewed intake.
