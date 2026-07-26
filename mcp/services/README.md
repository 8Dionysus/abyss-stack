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
| [`abyss-machine-mcp`](abyss-machine-mcp/README.md) | compact owner-aware machine brief, host evidence map, resource/memory/typing/nervous read models, non-mutating route preflight |
| [`aoa-session-memory-mcp`](aoa-session-memory-mcp/README.md) | `.aoa` session search, route traces, atlas map lookup, graph/GraphRAG evidence packets, quality samples, freshness checks, and diagnostics |
| [`tos-corpus-mcp`](tos-corpus-mcp/README.md) | Tree of Sophia corpus index and philosophy graph projection status, graph-view packets, resource search, node lookup, relation-pack access, and philosophy neighborhoods |
| [`aoa-4pda-connector-mcp`](aoa-4pda-connector-mcp/README.md) | local 4PDA connector status, source-route, graph/hybrid query, and answer packets preserving evidence-chain fields |
| [`aoa-telegram-connector-mcp`](aoa-telegram-connector-mcp/README.md) | local Telegram connector status, source-route, graph query, and answer packets preserving permission/evidence reports |
| [`aoa-discord-connector-mcp`](aoa-discord-connector-mcp/README.md) | local Discord connector status, source-route, graph query, and answer packets preserving permission/evidence reports |

## Local transport lifecycle

Every package keeps stdio as its portable default. A host may explicitly set
`AOA_MCP_TRANSPORT=streamable-http` to run one shared owner process, but the
server rejects any `AOA_MCP_HOST` outside `127.0.0.1`, `localhost`, or `::1`.
HTTP also requires `AOA_MCP_HTTP_BEARER_TOKEN` or the systemd credential
`aoa-mcp-http-bearer-token`; missing, short, malformed, or conflicting values
fail before bind. Standalone package manifests require `mcp>=1.27.2,<2`, the
SDK line on which this FastMCP bearer contract is exercised. This route is
authenticated local transport consolidation, not network publication. Remote,
wildcard-bind, gateway, proxy, cross-host, and OAuth/federated identity
topology require a later decision than
[D-0077](../../docs/decisions/ABYSS-STACK-D-0077-loopback-mcp-owner-lifecycle.md).

The shared credential and `mcp:access` scope are transitional. They prove that
an unauthenticated local caller is rejected, but they do not separate owners
or effects and therefore cannot admit an effectful capability. The governed
organ-access target in
[D-0087](../../docs/decisions/ABYSS-STACK-D-0087-owner-bounded-mcp-access-fabric.md)
uses per-owner, per-policy-plane credentials and process contours. Until that
implementation and its proof land, current services remain direct shadow
access planes even when their read calls work.

| Owner instance | Default port |
|---|---:|
| `aoa-decisions` | 5420 |
| `aoa-memo` | 5421 |
| `aoa-session-memory` | 5422 |
| `abyss-machine` | 5423 |
| `aoa-evals` | 5424 |
| `aoa-kag` | 5425 |
| `aoa-4pda-connector` | 5426 |
| `aoa-telegram-connector` | 5427 |
| `aoa-discord-connector` | 5428 |
| `tos-corpus` | 5429 |
| `aoa-stats` | 5430 |
| `abyss-stack` read | 5431 |
| PostgreSQL storage module (non-MCP; reserved conflict) | 5432 |
| `abyss-stack` candidate | 5433 |

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

`systemd/user/aoa-mcp-http@.service` owns one process per instance and launches
the deployed workspace wrapper, not a source checkout. The
`aoa-mcp-http.service` bundle wants the ten owner wrappers currently present in
the shared Codex plane, including `aoa-stats`. `tos-corpus` implements the same
guarded transport contract but remains outside the bundle until its workspace
wrapper and live canary are source-owned. Installing units only links and
reloads them; starting or restarting an owner is a separate operator action
after source/deployed parity. Credential provisioning and Codex client-install
routes remain owned by the systemd route card and executable installer.

The provision route creates a missing `Secrets/Configs` directory privately,
preserves an existing directory's permissions, and rejects symlinked secret
roots or credential files.

Codex HTTP entries keep only the environment-variable name in config:

```toml
[mcp_servers.aoa_session_memory]
url = "http://127.0.0.1:5422/mcp"
bearer_token_env_var = "AOA_MCP_HTTP_BEARER_TOKEN"
```

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
