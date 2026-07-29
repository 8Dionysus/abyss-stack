# Connector Read Contour Isolation

- Decision ID: ABYSS-STACK-D-0093
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mcp/services/aoa-*-connector-mcp/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP access plane, connector adapter, local evidence
- Stack lanes: MCP services, organ access fabric, runtime lifecycle
- Mechanic parents: runtime-lifecycle
- Guard families: owner credential, effect isolation, network denial, tool allowlist
- Posture: accepted source connector-read isolation

## Context

Six connector owners are intended to become OS Abyss evidence organs through
MCP: 4PDA, Telegram, Discord, Course, StackOverflow, and XDA. Their current
owner contracts are not identical:

- 4PDA, Telegram, Discord, StackOverflow, and XDA expose local packet-oriented
  CLI readers alongside collection, build, account, or mutation surfaces;
- Course already ships an independently runnable owner MCP dispatcher, but
  that dispatcher includes `connected_run` and other surfaces that may use
  network, browser, authentication, planning, refresh, or fixture execution;
- StackOverflow and XDA documentation mention a hybrid query, while their
  current owner CLIs do not implement `query-hybrid`.

The existing 4PDA, Telegram, and Discord OS adapters also shared the legacy
transport credential. A loopback listener and read-looking tool name do not
isolate one connector from another, exclude owner-side effects, or prove that
returned evidence came only from local packets.

## Options considered

1. Keep the shared connector credential and rely on tool descriptions and
   caller restraint.
2. Proxy each complete owner CLI or owner MCP catalog and let policy be chosen
   dynamically per request.
3. Give every connector a distinct authenticated read process, publish only a
   finite owner-verified local allowlist, enforce packet and process
   no-network/no-write boundaries, and fail closed when owner documentation
   and executable command shape disagree.

## Decision

Choose option 3.

4PDA, Telegram, and Discord retain their finite local read catalogs on ports
`5426`, `5427`, and `5428`. Course, StackOverflow, and XDA use ports `5436`,
`5437`, and `5438`, preserving `abyss-stack-mcp` on `5431`/`5433` and the
PostgreSQL reservation on `5432`.

Each connector has an exact bearer environment variable, systemd credential,
authorization scope, client identity, server identity, and observed tool
catalog. All tools declare read-only, non-destructive, idempotent, and
closed-world behavior. Managed processes use
`aoa-organ-mcp-read@.service`, which grants no persistent writable path and
denies non-loopback IP traffic.

The command-bridge adapters invoke only exact local packet readers and reject
query or answer packets that do not prove `network_touched=false` and
`read_only=true`. They expose no generic command dispatcher. Crawl, refresh,
materialize, build, import, login/session, private/account, attachment,
download, platform-write, and internal-search surfaces remain absent.

Course calls the owner MCP dispatcher directly so owner retrieval semantics
are not reimplemented, but publishes only nine explicitly reviewed read
tools. The wrapper verifies that the loaded owner module belongs to the
selected owner root, uses owner `StorageRoots`, forces source references off
where supported, verifies the exact owner result/tool identity, and requires
the current invocation's direct `network_touched=false` and `read_only=true`
attestation where the owner contract supplies one. Historical connected-run
receipts and unexecuted future plans may truthfully retain
`network_touched=true` as result data; they are not treated as effects of the
current read. Owner read tools that do not yet publish a direct invocation
attestation retain recursive denial of any network-use report. The adapter
excludes `connected_run` plus live, plan, auth, browser, refresh, and
fixture-effect tool surfaces.

StackOverflow and XDA do not publish `query-hybrid` until the executable owner
CLI implements it. Owner documentation alone cannot create an OS capability.
StackOverflow accepted-answer and score signals remain contextual evidence,
not truth.

## Rationale

The connector family has one durable access law while retaining owner-specific
meaning and constraints. Exact credentials prevent cross-owner bearer reuse;
finite catalogs prevent CLI or owner-MCP growth from silently widening the OS
surface; application packet checks and the systemd sandbox provide independent
effect controls.

Filtering the Course owner dispatcher preserves its canonical retrieval
implementation without importing its connected execution authority. Failing
closed on StackOverflow/XDA contract-versus-CLI drift prevents a documented
future route from becoming a fabricated current tool.

This shape costs one process, credential, and explicit admission path per
connector, but makes lifecycle, rollback, and acceptance evidence attributable
to the actual organ rather than to a shared connector bucket.

## Consequences

- The credential provisioner now manages fourteen owner-read credentials and
  two Memo/Evals candidate credentials and rejects equality across all sixteen
  values.
- The default organ bundle names fifteen direct processes: seven non-connector
  read instances, six connector read instances, and two candidate instances.
  ToS remains credential-staged outside the bundle; both stack-owned MCP
  planes remain separate from it.
- Adding an owner command or tool requires an explicit OS allowlist and test
  change; package discovery cannot expand the catalog.
- A future effectful connector capability requires a separate process,
  credential, approval model, receipt, rollback proof, and decision. It cannot
  be added to these read contours.
- The inspected local owner checkouts were behind their remote source refs.
  The final integrated landing must reverify exact owner revisions before
  acceptance.
- These are unlanded source candidates. They do not prove package deployment,
  process health, endpoint readiness, consumer registration, authentication
  denial, grounded results, owner acceptance, benefit, or rollback.

## Relationship to prior decisions

- Applies the owner/policy-plane law from `ABYSS-STACK-D-0087`.
- Extends the behavior-first isolation sequence from
  `ABYSS-STACK-D-0089` through `ABYSS-STACK-D-0092`.
- Keeps source meaning and acceptance in each connector owner; MCP remains an
  access plane.

## Source surfaces

- `mcp/services/aoa-4pda-connector-mcp/`
- `mcp/services/aoa-telegram-connector-mcp/`
- `mcp/services/aoa-discord-connector-mcp/`
- `mcp/services/aoa-course-connector-mcp/`
- `mcp/services/aoa-stackoverflow-connector-mcp/`
- `mcp/services/aoa-xda-connector-mcp/`
- `mcp/services/_shared/build_http_auth_vendors.py`
- `mcp/services/_shared/codex_http_client.sh`
- `systemd/user/aoa-organ-mcp-read@.service`
- `systemd/user/aoa-mcp-http.service`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`

## Follow-up route

Keep all six connectors shadow in O1. During the final integrated landing,
reverify current owner contracts, package and deploy the exact source, inspect
each observed catalog, prove cross-owner authentication denial and process
confinement, call only non-network local canaries, obtain owner acceptance,
and prove per-owner rollback before changing any registry maturity axis.
