# Machine Diagnostic Effect Isolation

- Decision ID: ABYSS-STACK-D-0089
- Status: accepted
- Date: 2026-07-26
- Owner surface: `docs/decisions/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP access plane, host bridge, machine diagnostics
- Stack lanes: MCP services, machine fit, runtime lifecycle
- Mechanic parents: machine-fit, runtime-lifecycle
- Guard families: effect isolation, owner credential, filesystem read-only
- Posture: accepted machine read-contour correction

## Context

`ABYSS-STACK-D-0036` established a read-only `abyss-machine-mcp` access plane.
Later inspection of the current owner CLI showed that several allowlisted
commands named status, recall, trace, coverage, or validation persist
generated/latest files, histories, indexes, or evidence packs. The MCP
catalog nevertheless labelled every route `mutates: false`.

Under the owner-bounded fabric in `ABYSS-STACK-D-0087`, JSON output and
non-destructive intent are not sufficient for read admission. The actual owner
implementation and its transitive persistent effects decide the contour.

## Options considered

1. Keep the broad catalog and rely on documentation that effects are minor.
2. Give the read unit writable generated-state paths.
3. Add `--no-write` flags to every owner CLI path before changing the MCP.
4. Shrink the MCP read contour to proven reads/no-write calls now, record
   effectful historical names as withdrawn, and design any future effect
   contour separately.

## Decision

Choose option 4.

The machine MCP read contour exposes only a finite command allowlist:

- existing latest/static reads;
- owner routes whose implementation is non-persistent;
- `resource plan` with mandatory `--no-write`;
- artifact trust gate and registry-latest reads.

`stack-bridge` reads `stack-bridge latest` rather than refreshing the export.
Composite route planning no longer calls the CLI `processes game-guard`
command because it writes latest state; the owner memory plan already obtains
that input transitively with `write_latest=False`.

Historical effectful names fail before the command runner and remain visible
in the catalog as withdrawn. Nervous recall and RAG trace tools are removed
from the server catalog. No machine internal-effect MCP is admitted by this
decision.

The loopback read process uses:

- `ABYSS_MACHINE_MCP_READ_BEARER_TOKEN`;
- `abyss-machine-mcp-read-bearer-token`;
- `mcp:abyss-machine:read`;
- `aoa-loopback-codex:abyss-machine:read`;
- `aoa-organ-mcp-read@abyss-machine.service`.

The unit keeps the filesystem read-only and has no persistent writable path.

## Rationale

Filesystem hardening must agree with the advertised tool semantics. Giving a
read process writable generated-state paths would turn a naming mistake into a
security policy. Waiting for every owner CLI route to gain a no-write option
would leave the overbroad access plane in place. A smaller proven catalog is
therefore the honest intermediate state and preserves a clean path to later
owner-controlled effect contours.

## Consequences

- A read caller cannot refresh host generated state through a generic surface
  name, dedicated tool, resource, or prompt.
- Some previously advertised diagnostics are intentionally unavailable through
  MCP until the owner CLI offers a proven no-write path or a separately
  governed effect process is designed.
- Source correctness does not establish deployment, registration, invocation,
  benefit, maturity, or owner acceptance.
- A future machine effect contour requires a distinct process, credential,
  catalog, filesystem allowlist, approval, receipt, postcondition, rollback,
  and a later decision.

## Relationship to prior decisions

- Narrows the surface admitted by `ABYSS-STACK-D-0036`; it does not replace
  the access-plane ownership split.
- Uses the authenticated loopback lifecycle from `ABYSS-STACK-D-0077`.
- Applies the owner/effect separation law from `ABYSS-STACK-D-0087`.
- Mirrors the cache-effect isolation principle in `ABYSS-STACK-D-0088`.

## Source surfaces

- `mcp/services/abyss-machine-mcp/src/abyss_machine_mcp/core.py`
- `mcp/services/abyss-machine-mcp/src/abyss_machine_mcp/server.py`
- `mcp/services/abyss-machine-mcp/tests/test_machine_mcp.py`
- `systemd/user/aoa-organ-mcp-read@.service`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `/srv/AbyssOS/abyss-machine/src/abyss_machine/cli.py`

## Follow-up route

Keep the machine owner in shadow until package, deploy, process, endpoint,
consumer, proof, acceptance, rollback, and post-merge verification gates are
completed in the final integrated rollout.
