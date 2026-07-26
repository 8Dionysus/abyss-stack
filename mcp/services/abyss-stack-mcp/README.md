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

Both read tools are server-filtered to `policy_family=read`; omitting the
catalog filter cannot enumerate candidate or effect subjects, and inspection
rejects every higher-policy contour before loading an observation.

The candidate process exposes only:

- `stack_prepare_runtime_plan`: a content-addressed `sync`, `deploy`,
  `activate`, `restart`, or `rollback` candidate.

The processes use different tools, default ports (`5431`, `5433`), environment
variables, systemd credential names, scopes, and client identities. A read
credential cannot authenticate to or enumerate the candidate process.

Every candidate remains `execution_authorized=false`, requires separate human
approval before any effect, contains no free-form shell command, expires in at
most ten minutes, and stops on observation drift or precondition mismatch.
Every plan requires usable subject freshness. Activation additionally requires
an active process with an observed process identity, a ready endpoint, a
registered consumer with the exact server schema digest and an overlapping MCP
protocol version, named acceptance-owner evidence bound to the current source
revision and package digest, a grounded canary, and usable rollback proof. The
acceptance receipt and selected compatible consumer's exact `registration_ref`
are embedded in activation steps and copied into the expiring precondition
evidence. Rollback requires
usable registry, selected consumer-registration, canary-route, and rollback
evidence, embeds the selected registration target, and carries every one of
those proofs into the candidate. A ready rollback proof must identify the
complete last-known-good consumer registration, package, deploy revision and
tree, unit, credential class, executable, and process identity. Its ordered
steps first deny discovery and activation, restore that runtime floor, restore
the consumer registration, and finally run the grounded canary. Restart plans
also require and carry usable canary-route evidence. A plan expires at the
earliest of ten minutes, its observation/freshness envelopes, every required
link, and every copied evidence ref; it cannot outlive its proof. Candidate
planning allows at most 30 seconds of positive clock skew and rejects
future-dated observations, required links, evidence refs, freshness, or deploy
timestamps beyond it.

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
The generated Draft 2020-12 schema includes the conditional invariants for
usable links and freshness, endpoint readiness, consumer registration,
active-process identity, accepted-target completeness, successful canaries,
rollback readiness, and policy/effect pairing. The Pydantic loader remains the
final authority for loopback endpoint parsing, relative clock-skew, relational
timestamp, acceptance-owner provenance, target matching, uniqueness, and
content-address checks that JSON Schema cannot express.

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

The managed user units do not use ambient Python. After syncing the package to
`Configs`, provision the source-addressed runtime explicitly:

```bash
scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime
```

This creates or refreshes
`${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv`, verifies its dependencies,
and records the exact deployed-package content digest. Repeating the command
with unchanged source verifies and reuses the environment. The units have a
`ConditionPathExists` guard plus an executable `ExecCondition`, and remain
inactive when this runtime is absent or unusable.
They execute the package installed inside that venv, not `Configs/src`.
Consequently, a later Configs sync cannot mix new code with an older dependency
closure; the synced package becomes eligible for a later start only after this
explicit reprovision step succeeds.

## Validation

Run the commands in [AGENTS.md](AGENTS.md).
