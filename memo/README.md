# abyss-stack Memo Port

This is the local memory port for `abyss-stack`.

It is for runtime-side memory candidates and handoff receipts. Durable reviewed
memory remains in `aoa-memo`; raw session evidence remains in `.aoa`; MCP access
is exposed through `mcp/services/aoa-memo-mcp/`.

## Layout

| Path | Use |
|---|---|
| `PORT.yaml` | local port contract for owner, mode, routes, validators, and vocabulary extensions |
| `INDEX.md` / `index.min.json` | generated local read model over packets |
| `candidates/` | proposed memory claims with evidence refs |
| `receipts/` | review, validation, accept, reject, or forward traces |
| `exports/` | reviewed-intake packets for `aoa-memo` |
| `local/` | stack-local memory that should remain local for now |

Default write mode: `write_candidate_only`.

To create a candidate through the MCP helper:

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli create-candidate \
  --repo abyss-stack \
  --evidence-ref mechanics/federation-seams/parts/memo-seam/docs/MEMO_RUNTIME_SEAM.md \
  --claim "Runtime memory access should route through reviewed local candidates."
```

Then validate the emitted candidate path with:

```bash
PYTHONPATH=mcp/services/aoa-memo-mcp/src python -m aoa_memo_mcp.cli validate-candidate path/to/candidate.json
```
