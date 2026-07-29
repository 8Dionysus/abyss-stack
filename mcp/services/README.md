# MCP Services

`mcp/services/` contains runnable stack-owned MCP service packages.

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
The legacy template still accepts `AOA_MCP_HTTP_BEARER_TOKEN` and
`aoa-mcp-http-bearer-token` only as compatibility transport. Current organ
read contours use exact owner-and-policy token variables, credential names,
scopes, and client identities for Decisions, Memo, Evals, KAG, Stats, Abyss
Machine, Session Memory, ToS corpus, and all six connector adapters. Memo and
Evals additionally use distinct candidate credentials and processes. Missing,
short, malformed, cross-owner, cross-contour, or conflicting
values fail before bind. Standalone package
manifests require `mcp>=1.27.2,<2`, the SDK line on which this FastMCP bearer
contract is exercised. This route is authenticated local transport
consolidation, not network publication. Remote, wildcard-bind, gateway, proxy,
cross-host, and OAuth/federated identity topology require a later decision than
[D-0077](../../docs/decisions/ABYSS-STACK-D-0077-loopback-mcp-owner-lifecycle.md).

The remaining shared credential and `mcp:access` scope are compatibility-only.
They prove that an unauthenticated local caller is rejected, but they do not
separate owners or effects and therefore cannot admit an organ capability. The governed
organ-access target in
[D-0087](../../docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md)
uses per-owner, per-policy-plane credentials and process contours. Decisions,
Memo, Evals, KAG, Stats, Abyss Machine, Session Memory, ToS corpus, 4PDA,
Telegram, Discord, Course, StackOverflow, and XDA now have source-level read
isolation. Memo and Evals also have source-level candidate process isolation
with finite write allowlists. They remain shadow until package, deploy,
consumer, proof, acceptance, and rollback gates pass.

| Owner instance | Default port |
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

`abyss-stack-mcp` does not join the transitional shared owner credential. Its
read and candidate planes select distinct credential names, scopes, client
identities, ports, and tool catalogs. The candidate plane only prepares
content-addressed plans and has no dispatch method. Neither plane is included
in the existing owner bundle until package/deploy provenance, a live
observation, consumer canary, and rollback evidence are present.
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

`systemd/user/aoa-mcp-http@.service` remains a compatibility template only.
`systemd/user/aoa-organ-mcp-read@.service` owns the filesystem-read-only
Decisions, Memo, Evals, KAG, Stats, Abyss Machine, Session Memory, and six
connector process contours. Dedicated Memo and Evals candidate units add only
their finite local-port write paths. All units launch deployed workspace
wrappers, not a source checkout. The `aoa-mcp-http.service` bundle wants
fifteen direct processes across these contours. `tos-corpus` has the same
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

The client install adds one bounded function to the target user's `.zshrc`.
For each new interactive `codex` launch, that function delegates to the
deployed source-owned launcher, which validates the credential and places it
only in the Codex process environment before `exec`. It does not replace the
Codex installer symlink, export the bearer into the parent shell, or alter
already running shells and sessions. Remove only this managed route with
`scripts/aoa-install-systemd --remove-mcp-http-codex-client`.

The systemd owner receives the same value via `LoadCredential`, so neither the
unit, `.zshrc`, nor `config.toml` contains the secret. This bearer prevents
unauthenticated local callers; it does not sandbox a compromised same-UID
process that already has access to the operator's Secrets tree.

For district law, read [AGENTS](AGENTS.md). For the parent access-plane route,
read [mcp/AGENTS](../AGENTS.md).
