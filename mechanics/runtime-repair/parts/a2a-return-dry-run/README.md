# Runtime Repair Surface Contracts

This part owns the A2A return closeout dry-run doc, runtime contract, example,
and focused tests.

- `docs/A2A_RETURN_DRY_RUN.md`
- `aoa_a2a_return_closeout_dry_run.py`
- `schemas/runtime-a2a-return-closeout-dry-run.schema.json`
- `examples/runtime_a2a_return_closeout_dry_run.example.json`
- `tests/test_a2a_return_closeout_dry_run.py`

The local request family is `a2a-return-closeout`. Older SDK wire input is
accepted only as an upstream compatibility request kind routed through
`mechanics/federation-seams/parts/federation-checks/docs/UPSTREAM_COMPATIBILITY.md`.
