# Validation

Run:

```bash
python mcp/protocol-lab/scripts/build_protocol_lab_status.py
python mcp/protocol-lab/scripts/build_protocol_lab_status.py --check
python mcp/protocol-lab/scripts/validate_protocol_lab.py
python -m pytest -q mcp/protocol-lab/tests
python -m ruff check mcp/protocol-lab
python mcp/protocol-lab/scripts/protocol_watcher.py \
  --state-root /srv/abyss-machine/cache/mcp-protocol-watch-observation
```

The validator checks exact P1 gate order, final spec and stable next-SDK pins,
stable registration retention, read-only pilot isolation, unchanged production
stack pins, the normalized Codex wire receipt, exact SDK conformance, the
bounded isolated KAG adapter, requestState-handle, catalog-cache, propagated
cancellation, stable modern Codex, rollback, frozen-revision conformance,
watch-plan schemas, Tasks non-support, unproved residuals, and generated-status
freshness.

It also validates the public-safe 11-case Tasks adapter receipt, including
durable restart recovery and the real read-only owner diagnostic, while
requiring production enablement, Codex consumption, and notifications to stay
false.

The Tasks matrix validator additionally requires exactly one bounded row for
Codex, Inspector, Python, TypeScript, Go, Rust rmcp, C#, and the pre-final
reference extension. It binds the released `rmcp 3.1.2` strict-pair pass and
the Inspector `2.1.0` missing-`Mcp-Name` blocker to normalized source fixtures,
while keeping core-read migration independent and production Tasks disabled.

The watcher command performs current network observation and writes immutable
private evidence plus a path-free normalized public-safe verdict. Its tests
prove the public projection contains no temporary or machine-local path. It
does not execute a
lab unless `--execute` and a regular mode `0600` runtime config are both
provided. Passing these commands proves only that the source gate and current
refresh signals are internally consistent. It does not prove production
admission, Tasks support, effectful handles, cross-replica cache invalidation,
or deployed cutover.
