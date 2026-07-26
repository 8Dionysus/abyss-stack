# abyss-stack-mcp

`abyss-stack-mcp` is the stack-owned evidence plane for MCP runtime topology.
It answers questions about the chain from reviewed source through package,
deploy, process, endpoint, registry, consumer schema observation, grounded
canary, and rollback readiness.

It is not a gateway, does not proxy owner tools, does not flatten nested state
into `healthy`, and does not own proof, memory, source truth, or owner
acceptance.

## Process contours

The read process exposes only:

- `stack_runtime_catalog`: compact discovery with zero detail-schema bytes;
- `stack_runtime_inspect`: one exact owner/policy target and one selected
  evidence view.

The candidate process exposes only:

- `stack_prepare_runtime_plan`: a content-addressed `sync`, `deploy`,
  `activate`, `restart`, or `rollback` candidate.

The processes use different tools, default ports (`5431`, `5432`), environment
variables, systemd credential names, scopes, and client identities. A read
credential cannot authenticate to or enumerate the candidate process.

Every candidate remains `execution_authorized=false`, requires separate human
approval before any effect, contains no free-form shell command, expires in at
most ten minutes, and stops on observation drift or precondition mismatch.

## Observation input

Set `ABYSS_STACK_MCP_OBSERVATION_PATH` to one explicit secret-free
`abyss_stack_runtime_observation_v1` file. The default live route is:

```text
/srv/AbyssOS/abyss-stack/Logs/mcp/organ-runtime-observation.json
```

The loader rejects symlinks, non-files, payloads above 2 MiB, unknown contract
fields, secret-like keys or values, shared credential classes, non-loopback
HTTP endpoints, and unsupported effect classes. Expired observations remain
visible as stale read evidence but cannot produce a candidate plan.

The committed example is fictional and public-safe. It is neither a live
runtime capture nor admission evidence.

## Portable use

```bash
python -m pip install -e mcp/services/abyss-stack-mcp
abyss-stack-mcp --observation-path /path/to/observation.json catalog
ABYSS_STACK_MCP_POLICY_FAMILY=read abyss-stack-mcp-server
```

Stdio is the portable default. Authenticated loopback Streamable HTTP is
selected through `AOA_MCP_TRANSPORT=streamable-http`; it requires the
plane-specific credential.

## Validation

Run the commands in [AGENTS.md](AGENTS.md).
