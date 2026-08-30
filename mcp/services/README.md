# MCP Services

`mcp/services/` contains runnable stack-owned MCP service packages.  The
shared runtime catalog in
[`_shared/runtime-config.v1.json`](_shared/runtime-config.v1.json) owns the
MCP SDK major line, protocol revision, transport, contour, port, credential,
and deployment identities; package code and operational probes consume its
generated projections.

Use this district for service packages with their own source, tests, local
route card, and validation path.

| Service | Use for |
|---|---|
| [`abyss-stack-mcp`](abyss-stack-mcp/README.md) | stack-owned source/package/deploy/process/endpoint/consumer observations and non-executing runtime-plan candidates |
| [`aoa-memo-mcp`](aoa-memo-mcp/README.md) | memory briefs, local memo port status, candidate creation and validation, session rehydration pointers |
| [`aoa-decisions-mcp`](aoa-decisions-mcp/README.md) | fresh workspace decision graph status, search, repo slices, decision neighborhoods, and task packets |
| [`aoa-evals-mcp`](aoa-evals-mcp/README.md) | bounded eval selection, bundle inspection, comparison readers, runtime evidence templates, candidate-only report skeletons |
| [`aoa-kag-mcp`](aoa-kag-mcp/README.md) | owner-aware discovery, exact/vector/graph search, addressed reads, bounded traversal, and evidence explanation |
| [`aoa-stats-mcp`](aoa-stats-mcp/README.md) | federated stats catalog, owner-local port inspection, compact boundaries, and packet compatibility |
| [`abyss-machine-mcp`](abyss-machine-mcp/README.md) | compact owner-aware machine brief, finite no-write host diagnostics, existing latest projections, and non-mutating route preflight |
| [`aoa-session-memory-mcp`](aoa-session-memory-mcp/README.md) | `.aoa` session search, route traces, atlas map lookup, graph/GraphRAG evidence packets, quality samples, freshness checks, and diagnostics |
| [`tos-corpus-mcp`](tos-corpus-mcp/README.md) | Tree of Sophia corpus index and philosophy graph projection status, graph-view packets, resource search, node lookup, relation-pack access, and philosophy neighborhoods |
| [`aoa-4pda-connector-mcp`](aoa-4pda-connector-mcp/README.md) | local 4PDA connector status, source-route, graph/hybrid query, and answer packets preserving evidence-chain fields |
| [`aoa-telegram-connector-mcp`](aoa-telegram-connector-mcp/README.md) | local Telegram connector status, source-route, graph query, and answer packets preserving permission/evidence reports |
| [`aoa-discord-connector-mcp`](aoa-discord-connector-mcp/README.md) | local Discord connector status, source-route, graph query, and answer packets preserving permission/evidence reports |
| [`aoa-course-connector-mcp`](aoa-course-connector-mcp/README.md) | filtered owner-MCP course status, source routing, answers, lesson context, graph, freshness, and evidence reports without connected execution |
| [`aoa-stackoverflow-connector-mcp`](aoa-stackoverflow-connector-mcp/README.md) | local StackOverflow status, source-route, graph query, and answer packets preserving evidence and score-signal context |
| [`aoa-xda-connector-mcp`](aoa-xda-connector-mcp/README.md) | local XDA status, source-route, graph query, and answer packets preserving owner evidence |

## Local transport lifecycle

Every package keeps stdio as its portable default. A host may explicitly set
`AOA_MCP_TRANSPORT=streamable-http` to run one owner process, but the server
rejects any `AOA_MCP_HOST` outside `127.0.0.1`, `localhost`, or `::1`.
Every standalone package also binds `serverInfo.version` to its own embedded
application version, kept equal to that package's `pyproject.toml`. Source-local
wrappers therefore report the code they actually imported instead of ambient
metadata from an older installed wheel. The MCP SDK version is dependency
evidence, not the deployed service identity used by canary and provenance
checks.
The retired shared template is a non-startable tombstone and accepts no
transport or credential. Current organ read contours use exact
owner-and-policy token variables, credential names,
scopes, and client identities for Decisions, Memo, Evals, KAG, Stats, Abyss
Machine, Session Memory, ToS corpus, and all six connector adapters. Memo and
Evals additionally use distinct candidate credentials and processes. Missing,
short, malformed, cross-owner, cross-contour, or conflicting
values fail before bind. Standalone package manifests admit only the MCP 2.x
line (`mcp>=2,<3`); the deterministic deployment lock currently tests
`mcp==2.1.1` with the paired `mcp-types==2.1.1`. That SDK line implements the
`2026-07-28` server/discovery and
streamable-HTTP contract. The shared
`_modern_runtime.py` projection preserves the standalone package shape while
binding every organ server to the same fail-closed modern runtime and bearer
contract. This route is authenticated local transport
consolidation, not network publication. Remote, wildcard-bind, gateway, proxy,
cross-host, and OAuth/federated identity topology require a later decision than
[D-0077](../../docs/decisions/ABYSS-STACK-D-0077-loopback-mcp-owner-lifecycle.md).

The preserved shared credential and `mcp:access` scope are offline rollback
material only. No managed service loads them, so they cannot admit or launch an
organ capability. The governed
organ-access target in
[D-0087](../../docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md)
uses per-owner, per-policy-plane credentials and process contours. Decisions,
Memo, Evals, KAG, Stats, Abyss Machine, Session Memory, ToS corpus, 4PDA,
Telegram, Discord, Course, StackOverflow, and XDA now have source-level read
isolation. Memo and Evals also have source-level candidate process isolation
with finite write allowlists. Eleven read contours are currently admitted:
Stack, Machine, Decisions, Memo, Session Memory, Evals, KAG, Stats, 4PDA,
Telegram, and Discord. ToS, Course, StackOverflow, XDA, every candidate
contour, and the internal-effect contour remain shadow/unadmitted until their
own package, deploy, consumer, proof, acceptance, and rollback gates pass.

The values in the following table document the catalog; they are not a second
configuration source. The authoritative declaration is
[`_shared/runtime-config.v1.json`](_shared/runtime-config.v1.json), checked by
its schema, loader, and generated package projections.

| Owner instance | Catalog port |
|---|---:|
| `aoa-decisions` | 5420 |
| `aoa-memo` read | 5421 |
| `aoa-session-memory` | 5422 |
| `abyss-machine` | 5423 |
| `aoa-evals` read | 5424 |
| `aoa-kag` | 5425 |
| `aoa-4pda-connector` | 5426 |
| `aoa-telegram-connector` | 5427 |
| `aoa-discord-connector` | 5428 |
| `tos-corpus` | 5429 |
| `aoa-stats` | 5430 |
| `abyss-stack` read | 5431 |
| PostgreSQL storage module (non-MCP; reserved conflict) | 5432 |
| `abyss-stack` candidate | 5433 |
| `aoa-memo` candidate | 5434 |
| `aoa-evals` candidate | 5435 |
| `aoa-course-connector` | 5436 |
| `aoa-stackoverflow-connector` | 5437 |
| `aoa-xda-connector` | 5438 |
| `abyss-stack` internal-effect pilot | 5439 |

`abyss-stack-mcp` does not use the retired shared owner credential. Its
read, candidate, and exact internal-effect planes select distinct credential
names, scopes, client identities, ports, and tool catalogs. The candidate
plane only prepares content-addressed plans and has no dispatch method. The
effect plane exposes only the approved read-service restart-and-rollback pilot
on port `5439`; it cannot select a unit, command, or external effect. None of
the stack planes belongs to the shared owner bundle. The read plane is
separately admitted and active; candidate and internal-effect planes remain
inactive and unadmitted even though their discovery protocol is modern-only.
The managed units use the explicitly provisioned
`${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv` runtime rather than ambient
Python. `scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime`
creates or refreshes it from the deployed package and does not start a unit.
Link and reload the managed user units first: each stack plane holds a shared
runtime lock for its full lifetime, while changed provisioning holds the
exclusive lock and rechecks stopped state immediately before the environment
swap. Unit link/reload and provisioning are separate transactions, and the
runtime is installed only from a private digest-matched snapshot of deployed
source and lock material. The two contour bearers are also compared and cannot
share one value.

`systemd/user/aoa-mcp-http@.service` is a non-startable tombstone for the
retired ambient-Python/shared-bearer route. It contains no server command,
credential load, transport, or install target.
`systemd/user/aoa-organ-mcp-read@.service` owns the filesystem-read-only
Decisions, Memo, Evals, KAG, Stats, Abyss Machine, Session Memory, and six
connector process contours. Dedicated Memo and Evals candidate units add only
their finite local-port write paths. All units launch deployed workspace
wrappers, not a source checkout. The `aoa-mcp-http.service` bundle wants the
catalog-declared admitted client-read contours; candidate and effect contours
are never bundle startup dependencies. `tos-corpus` has the same
source-level read credential and safety contract but remains outside the
bundle until its workspace wrapper and live canary are source-owned.
Installing units only links and reloads them; starting or restarting an owner
is a separate operator action after source/deployed parity. Credential
provisioning and Codex client-install routes remain owned by the systemd route
card and executable installer.

The provision route creates a missing `Secrets/Configs` directory privately,
preserves an existing directory's permissions, and rejects symlinked secret
roots or credential files.

Codex HTTP entries keep only the environment-variable name in config:

```toml
[mcp_servers.aoa_session_memory]
url = "http://127.0.0.1:5422/mcp"
bearer_token_env_var = "AOA_SESSION_MEMORY_MCP_READ_BEARER_TOKEN"
```

Every migrated read entry uses its exact owner variable, for example
`AOA_KAG_MCP_READ_BEARER_TOKEN`. A future ToS bundle admission uses
`TOS_CORPUS_MCP_READ_BEARER_TOKEN`;
provisioning that credential does not claim that the missing workspace wrapper
or live canary already exists.
Memo and Evals candidate registrations use separate names and endpoints:
`AOA_MEMO_MCP_CANDIDATE_BEARER_TOKEN` on `5434` and
`AOA_EVALS_MCP_CANDIDATE_BEARER_TOKEN` on `5435`.
Connector registrations likewise use exact owner variables; Course,
StackOverflow, and XDA occupy `5436`, `5437`, and `5438` so the stack MCP
ports and PostgreSQL reservation remain intact.

The client install adds one bounded function to the target user's `.zshrc` and
one managed user-scoped ChatGPT wrapper plus desktop entry. Interactive Codex
and future Desktop launches delegate to the same deployed source-owned
launcher, which validates the exact eleven read credentials, checks the
eleven-member modern read fleet, and places each credential only in the
selected child-process environment before `exec`. When the fleet is
incomplete, the launcher requests the bounded admission recovery oneshot
without waiting and starts the client immediately; MCP authority remains fail
closed without turning the operator client into a lifecycle lock.
Metadata-only Codex commands do not cause recovery. The launcher does not
replace the Codex installer symlink or packaged ChatGPT files, export a bearer
into the parent shell, persist bearer values in the desktop entry, or alter
already running shells and sessions. Remove only these managed user-scoped
routes with
`scripts/aoa-install-systemd --remove-mcp-http-codex-client`.

The systemd owner receives the same value via `LoadCredential`, so neither the
unit, `.zshrc`, nor `config.toml` contains the secret. This bearer prevents
unauthenticated local callers; it does not sandbox a compromised same-UID
process that already has access to the operator's Secrets tree.

For district law, read [AGENTS](AGENTS.md). For the parent access-plane route,
read [mcp/AGENTS](../AGENTS.md).
