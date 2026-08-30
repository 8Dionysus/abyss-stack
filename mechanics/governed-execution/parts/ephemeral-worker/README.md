# Ephemeral Worker

This part is the `abyss-stack` runtime landing for the
`ephemeral_read_worker_v1` delegation class. It executes one explicitly
admitted, bounded read over immutable file coordinates and returns an
in-memory content-addressed result with raw economy observations.

The part also publishes two concrete `external_incarnation_v1` adapter
profiles: the first Codex CLI profile and a local/provider profile. They carry
the same `aoa_delegation_class_v1` ABI, but have different adapter identities
and remain runtime-owned. The profiles are descriptors; they do not launch a
model by themselves.

The source-backed descriptors live under `profiles/`; the Python factories and
focused tests must remain byte-equivalent to those descriptors.

The default profile is disabled. A caller must supply `activation: explicit`,
content digests for every input, and decoded-content plus encoded-transport byte
ceilings no larger than 16 MiB. Requests contain at most 1024 inputs and bound
request, holder, artifact-reference, and path strings to 4096 characters; path
spellings are normalized before duplicate rejection. The worker resolves each
absolute path from `/`
through descriptor-bound `O_DIRECTORY|O_NOFOLLOW` parents before opening the
basename, rejecting symlinked, traversal, unsupported, or non-regular paths;
it performs no workspace or runtime-state write. It preserves the parent
holder and never forms a role or transfers responsibility.

The Codex CLI adapter descriptor uses the exact `codex exec --json --disable
multi_agent` command shape. Adapter-pair validation rejects another
executable, wrong ABI values, and any command surface that enables or
ambiguously names the built-in lane.

The SDK class contract is the stronger ABI source:
`aoa-sdk/mechanics/boundary-bridge/parts/agent-incarnation-binding/`.
Role, mandate, model, eval, closeout, and acceptance meaning stays with the
named owner repositories.
