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
Provisioning validates the two existing or newly created bearer values
together and fails closed if they are identical.

Every candidate remains `execution_authorized=false`, requires separate human
approval before any effect, contains no free-form shell command, expires in at
most ten minutes, and stops on observation drift or precondition mismatch.
Every plan requires usable subject freshness. Activation additionally requires
an active process with an observed process identity, a ready endpoint, a
registered consumer with the exact server schema digest and an overlapping MCP
protocol version, a passed central-proof verdict issued by `proof_owner` and
bound to the current source revision and source-tree digest, package, deployed
revision and tree digest, schema, running process identity, consumer, and
exact canary route and receipt, named acceptance-owner evidence bound to the current source
revision and package digest, a grounded canary, and usable
rollback proof. Activation or restart of `internal_effect` and
`external_effect` targets is rejected because this package does not model
their separately required threat, approval, egress, compensation, or rollback
contracts. The central-proof and acceptance receipts plus the selected
compatible consumer's exact
`registration_ref` are embedded in ordered activation steps, preceded by exact
process-identity verification. A shadow registry receives an exact admission
action after those gates; an already admitted registry receives verification.
All receipts are copied into the expiring precondition evidence. Rollback requires
usable registry, selected consumer-registration, canary-route, and rollback
evidence, embeds the selected registration target, and carries every one of
those proofs into the candidate. A ready rollback proof must identify the
complete last-known-good consumer registration, package, deploy revision and
tree, unit, credential class, executable, process identity, and canary route
and receipt. The proof carries a second typed target that must exactly equal
that full restoration contour before readiness is accepted. Its ordered steps
first deny discovery and activation, restore that runtime floor, restore the
consumer registration, and finally run the proven last-known-good canary
rather than the current deployment's canary. Rollback planning relies on the
usable rollback proof that binds that LKG route and receipt; it neither validates
nor copies the current deployment's canary evidence, which may be failed,
blocked, or expired in the recovery scenario. Restart plans also require and
carry usable current-canary evidence and reject inactive processes, which must
use the full activation contour instead. A plan expires at the
earliest of ten minutes, its observation/freshness envelopes, every required
link, and every copied evidence ref; it cannot outlive its proof. Candidate
planning allows at most 30 seconds of positive clock skew and rejects
future-dated observations, required links, evidence refs, freshness, or deploy
timestamps beyond it. Required observations must also fall no later than 30
seconds after their enclosing observation snapshot, so an older snapshot
cannot carry causally newer proof. Activation and rollback causality checks use
only the exact proof-selected or last-known-good consumer; unrelated consumer
observations cannot veto a candidate and are not copied into it. Candidate
result freshness is the worst effective state across subject freshness and
every exact link the plan copies, so a drift-backed plan cannot claim `exact`.
Central proof cannot predate the canary link or evidence refs it names.
Duplicate evidence identities with conflicting `observed_at` values are
rejected before expiry deduplication.
Catalog and inspection apply the same 30-second future-skew bound to the
observation envelope, links, freshness, and nested evidence timestamps, using
the earlier of wall-clock time and the enclosing observation snapshot;
causally future usable evidence is reported as `blocked`, never as current,
before candidate planning is involved.
An expired observation envelope likewise downgrades both result metadata and
the derived catalog/freshness/drift fields to at least `stale_readable`, even
when the enclosed subject freshness expires later.
Inspection also folds the effective state of the selected evidence view into
result freshness metadata and exposes it beside the immutable raw owner state.
`rollback_required` is accepted only while its own link and evidence refs are
unexpired; a bare or expired rollback signal is a controlled precondition
failure.
Every plan also names one exact deployed-tree postcondition. Sync takes that
target from the reviewed source identity, deploy takes it from the exact
package identity, activate and restart preserve the observed deployed tree,
and rollback restores the last-known-good tree. The ordered sync/deploy
comparison step uses this future target rather than the pre-action deployed
digest. Rollback denies discovery for the exact registry ID and registry digest
observed by the candidate, not for a mutable registry name alone.

## Observation input

Set `ABYSS_STACK_MCP_OBSERVATION_PATH` to one explicit secret-free
`abyss_stack_runtime_observation_v1` file. The default live route is:

```text
/srv/AbyssOS/abyss-stack/Logs/mcp/organ-runtime-observation.json
```

The loader rejects symlinks, non-files, payloads above 2 MiB, unknown contract
fields, secret-like keys or values, shared credential classes, non-loopback
HTTP endpoints, credentials embedded in URI userinfo/path/query/fragment references,
encoded nested credential references, unparseable or excessively nested
URI-like references, whitespace-only exact targets, and unsupported effect
classes. Credential-key screening recognizes namespaced separator and
camel-case token sequences rather than only exact key spellings. Concatenated
matches require a recognized provider/consumer namespace or credential-value
attribute boundary, so ordinary keys such as `tokenizer`, `passwordless`, and
`authorizationPolicy` remain valid.
Secret-prefix checks ignore leading whitespace and cover the standard OpenAI,
GitHub, and GitLab token families, including GitLab personal, deploy, runner,
job, trigger, agent, workspace, SCIM, and feature-flag client tokens. Expired
observations remain visible as stale read evidence but cannot produce a
candidate plan.
The generated Draft 2020-12 schema includes the conditional invariants for
usable links and freshness, endpoint readiness, consumer registration,
active-process identity, accepted-target completeness, successful canaries,
central-proof target completeness, rollback readiness, and policy/effect
pairing. The Pydantic loader remains the final authority for loopback endpoint
parsing, relative clock-skew, relational timestamp, proof/acceptance-owner
provenance, target and proof-before-acceptance ordering, uniqueness, and
content-address checks that JSON Schema cannot express.

The committed example is fictional and public-safe. It is neither a live
runtime capture nor admission evidence.

## Portable use

```bash
python -m pip install -e mcp/services/abyss-stack-mcp
abyss-stack-mcp --observation-path /path/to/observation.json catalog
abyss-stack-mcp --observation-path /path/to/observation.json \
  inspect aoa-kag read --view proof
ABYSS_STACK_MCP_POLICY_FAMILY=read abyss-stack-mcp-server
```

Stdio is the portable default. Authenticated loopback Streamable HTTP is
selected through `AOA_MCP_TRANSPORT=streamable-http`; it requires the
plane-specific credential. Portable `catalog` and `inspect` are read-contour
commands; `plan` requires explicit `--policy-family candidate`.

The managed user units do not use ambient Python. After syncing the package to
`Configs`, first link and reload the lock-aware units, then provision the
source-addressed runtime explicitly:

```bash
scripts/aoa-install-systemd --all-user-units
scripts/aoa-install-systemd --provision-abyss-stack-mcp-runtime
```

These are intentionally separate transactions; combining both flags is
rejected so provisioning cannot run before the link-and-reload phase. The
standalone provision step verifies that both units are loaded from the
expected managed fragments and that user systemd's effective `ExecStart`
contains the exact shared runtime lock; absent, stale, or unexpectedly sourced
unit definitions fail closed and require another `daemon-reload`.
This creates or refreshes
`${AOA_STACK_ROOT}/Services/abyss-stack-mcp/venv`, installs the exact
`requirements.lock` closure with `--require-hashes`, verifies its dependencies,
and records a runtime identity composed from both the deployed-package digest
and the lock digest, plus a deterministic content digest of the installed
runtime files and symlink targets. Before that digest is recorded, generated
entry-point shebangs are rebound from the private staging directory to the
stable published venv path, so atomic publication does not leave launchers
pointing at a removed directory. Repeating the command with unchanged source
and lock rehashes the installed environment before verification and reuses it
only when the content digest still matches; missing or changed installed bytes
force a guarded rebuild. A changed identity is never installed
over a running plane: provisioning fails closed while either the read or
candidate unit is active or their user-systemd state cannot be observed. Stop
both units explicitly before reprovisioning, then start or canary them as a
separate action. The units have a
`ConditionPathExists` guard plus an executable `ExecCondition`, and remain
inactive when this runtime is absent or unusable.
Each unit holds a shared runtime lock for its full process lifetime. Changed
provisioning holds the exclusive lock, checks both unit states before the
build and again immediately before the guarded environment swap, and aborts if
a start races the build. Linking and reloading the committed units before
provisioning is therefore a required rollout precondition.
The provisioner copies the deployed package into a private staged snapshot,
requires that snapshot and its lock to match the initial digests, installs only
from the snapshot, and rechecks the deployed tree before writing the runtime
identity or swapping the environment. It also holds the same exclusive
source-projection lock that an applying MCP Configs sync holds for its complete
rsync transaction. A sync and provision transaction therefore cannot cross
each other's publication boundary or publish mixed or mislabelled runtime
bytes.
Every provisioner Python call clears inherited `PYTHONHOME`/`PYTHONPATH` and
uses isolated interpreter mode, including venv creation, pip installation,
dependency checks, and import verification.
They execute the package installed inside that venv, not `Configs/src`.
Both units clear ambient `PYTHONHOME`/`PYTHONPATH` and invoke the venv with
Python isolated mode, so a user-manager import override cannot precede the
measured site-packages.
Consequently, a later Configs sync cannot mix new code with an older dependency
closure; the synced package becomes eligible for a later start only after this
explicit reprovision step succeeds.

Runtime dependencies and the build backend are exact pins in
`requirements.constraints`; the committed `requirements.lock` carries the
resolved closure and artifact hashes. Regenerate it from the repository root
with the reviewed `pip-tools` version:

```bash
pip-compile --generate-hashes --resolver=backtracking --strip-extras \
  --all-build-deps --allow-unsafe \
  --constraint mcp/services/abyss-stack-mcp/requirements.constraints \
  --output-file mcp/services/abyss-stack-mcp/requirements.lock \
  mcp/services/abyss-stack-mcp/pyproject.toml
```

## Validation

Run the commands in [AGENTS.md](AGENTS.md).
