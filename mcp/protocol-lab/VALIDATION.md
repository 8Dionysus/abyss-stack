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
python mcp/protocol-lab/scripts/protocol_watcher.py \
  --plan mcp/protocol-lab/protocol-watch-plan.v1.json \
  --state-root /srv/abyss-machine/cache/mcp-protocol-watch-observation \
  --retention-plan
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

The retention plan command scans only the explicitly named watcher state root
and emits a private JSON dry run. It takes a shared lock only over an existing
lock file and does not create or chmod state. It does not remove anything. The
apply form (`--retention-apply`) is an operator action: it recomputes the plan
under the state lock, rechecks ownership, mount/device boundaries,
inode-deduplicated allocated bytes, same-user process references, unknown
top-level outputs, and protected references, then archives required receipts
before removing a completed run. Compact receipt archives are preserved by
default; their size is reported as a budget warning. The hourly deployed unit adds
`--apply-retention` to combine this apply step with its ordinary pass; source
validation and these tests never touch the deployed log root.
