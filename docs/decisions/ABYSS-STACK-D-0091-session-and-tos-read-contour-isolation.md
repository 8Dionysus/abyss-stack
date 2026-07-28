# Session Memory and ToS Read Contour Isolation

- Decision ID: ABYSS-STACK-D-0091
- Status: accepted
- Date: 2026-07-26
- Owner surface: `mcp/services/aoa-session-memory-mcp/` and
  `mcp/services/tos-corpus-mcp/`

## Index Metadata

- Original date: 2026-07-26
- Surface classes: MCP access plane, session evidence, ToS corpus
- Stack lanes: MCP services, organ access fabric, runtime lifecycle
- Mechanic parents: runtime-lifecycle
- Guard families: owner credential, filesystem read-only, effect isolation
- Posture: accepted source read-contour isolation

## Context

`aoa-session-memory-mcp` and `tos-corpus-mcp` were designed as read-only access
planes, but their optional HTTP transport still selected the transitional
shared bearer and `mcp:access` scope. Session Memory also had two direct
SQLite fast paths that opened generated search state through a normal
read-write connection even though they issued only queries.

The owner-bounded fabric in `ABYSS-STACK-D-0087` requires the process,
credential, filesystem, and observed tool catalog to agree. Read-only intent
or MCP annotations alone are insufficient.

`tos-corpus` has no deployed workspace wrapper or grounded live canary. Its
source package can be isolated now without pretending that the owner is
admitted to the default bundle.

## Options considered

1. Keep the shared bearer because both packages advertise read-only tools.
2. Add writable SQLite paths to the generic read unit for Session Memory.
3. Give each owner a distinct read credential, keep Session Memory SQLite
   fast paths explicitly read-only, and stage ToS without bundle admission.

## Decision

Choose option 3.

Session Memory uses:

- `AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN`;
- `aoa-session-memory-mcp-read-bearer-token`;
- `mcp:aoa-session-memory:read`;
- `aoa-loopback-codex:aoa-session-memory:read`;
- `aoa-organ-mcp-read@aoa-session-memory.service`.

Its MCP-local generated-state connections use SQLite URI `mode=ro` and
`PRAGMA query_only`. Owner CLI calls remain a finite argument construction:
MCP does not pass `--write`, `--write-report`, `--refresh-state`, `--apply`,
or another persistence switch. Maintenance commands returned in packets are
operator routes, not calls executed by MCP.

The ToS corpus adapter uses:

- `TOS_CORPUS_MCP_READ_BEARER_TOKEN`;
- `tos-corpus-mcp-read-bearer-token`;
- `mcp:tos-corpus:read`;
- `aoa-loopback-codex:tos-corpus:read`.

Every ToS tool publishes the closed-world read-only MCP annotation set and the
validator inspects the observed inventory. The source package is compatible
with `aoa-organ-mcp-read@tos-corpus.service`, but the bundle does not want that
instance until a source-owned deployed workspace wrapper and grounded live
canary exist.

The credential provisioner and Codex launcher include both owner-specific
read credentials and reject equality across the complete read set. A staged
credential does not prove deployment, process, endpoint, registration,
invocation, result freshness, benefit, maturity, or owner acceptance.

## Rationale

Owner-specific authentication makes cross-organ denial behavior testable.
Read-only SQLite connections align Session Memory's fast path with the
filesystem-read-only process sandbox instead of weakening the sandbox to fit
an implementation accident. Staging ToS source isolation while retaining its
wrapper/canary stop line preserves forward progress without laundering a
missing runtime link into admission.

## Consequences

- The shared bearer cannot authenticate to Session Memory or ToS corpus.
- Session Memory moves to the owner-read unit in the source bundle.
- ToS receives a staged owner-specific credential but remains outside the
  bundle.
- Existing Codex registrations must use the new named variables before their
  next canary; an already-running client is not proof of updated registration.
- Both owners remain registry shadows until the later package, deploy,
  process, endpoint, consumer, proof, acceptance, and rollback gates pass.

## Relationship to prior decisions

- Narrows the transport interpretation of `ABYSS-STACK-D-0037` and
  `ABYSS-STACK-D-0069`.
- Preserves the wrapper/canary gate from `ABYSS-STACK-D-0077`.
- Applies the owner/effect separation law from `ABYSS-STACK-D-0087`.
- Follows the behavior-first effect audits in `ABYSS-STACK-D-0089` and
  `ABYSS-STACK-D-0090`.

## Source surfaces

- `mcp/services/aoa-session-memory-mcp/src/aoa_session_memory_mcp/core.py`
- `mcp/services/aoa-session-memory-mcp/src/aoa_session_memory_mcp/server.py`
- `mcp/services/aoa-session-memory-mcp/tests/test_session_memory_mcp.py`
- `mcp/services/tos-corpus-mcp/src/tos_corpus_mcp/server.py`
- `mcp/services/tos-corpus-mcp/tests/test_tos_corpus_mcp.py`
- `systemd/user/aoa-organ-mcp-read@.service`
- `systemd/user/aoa-mcp-http.service`
- `mechanics/runtime-lifecycle/parts/user-unit/aoa_install_systemd.sh`
- `mcp/services/_shared/codex_http_client.sh`

## Follow-up route

Keep both owners shadow in the O1 registry. Admit Session Memory only after the
final integrated package/deploy/process/endpoint/consumer/proof/acceptance and
rollback sequence. Add ToS to the default bundle only after its separate
workspace-wrapper source route and grounded live canary exist.
