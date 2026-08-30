# Contract

## Request

`ephemeral-read-worker-request.schema.json` admits one explicit request with:

- `delegation_class: ephemeral_read_worker_v1`;
- `activation: explicit` (the default profile is `disabled`);
- one parent-holder content reference;
- an ordered, duplicate-free list of absolute regular-file inputs;
- a digest over the complete input list and byte ceilings;
- per-file content digests and per-file byte ceilings;
- separate decoded-content `max_output_bytes` and canonical encoded-result
  `max_transport_bytes` ceilings.

Every byte ceiling is a positive integer no larger than the supported 16 MiB
limit. The schema and runtime enforce this bound before opening an input, so a
schema-valid request cannot turn a platform-sized integer into an unbounded
read argument.

The worker validates the snapshot digest before opening any file. Paths must
use canonical non-empty components without `.` or `..`. It walks the absolute
path from `/` through no-follow directory descriptors, using
`O_PATH|O_DIRECTORY|O_NOFOLLOW` where available so execute-only parents remain
traversable, then opens the basename with `O_NOFOLLOW`; final or parent
symlinks, traversal spellings, and unsupported descriptor platforms fail
closed. It reads at most the declared ceilings and fails closed on content
drift.

## Result

`ephemeral-read-worker-result.schema.json` carries every returned artifact's
content digest and bounded bytes, the parent-holder reference, the result
digest, and raw observations for input bytes, output bytes, wall seconds,
turns, and executed commands. `actual_effects` is exactly `read_only`;
`responsibility_posture` is exactly `parent_retained`; role formation and
durable transfer are false.

The function returns this object in memory. Persisting or reviewing it belongs
to the caller and stronger owners. Runtime success is not an eval verdict,
closeout, acceptance, or economy-promotion claim.

`validate_ephemeral_read_result` is the producer-independent intake boundary.
For serialized input it enforces the transport ceiling before JSON parsing;
for every input form it bounds metadata and record cardinality, decodes
canonical base64, verifies byte counts and per-record digests, reconciles the
economy byte totals, and recomputes the packet result digest. It returns a deep
canonical copy only after those checks pass.

Mapped producer results apply the caller-provided transport ceiling to
cumulative base64 bytes before decoding. Schema-valid integral JSON counters
are accepted, booleans remain invalid, result text must be UTF-8 encodable,
and wall-time observations are finite and bounded to one supported year.

Digest schema definitions are exact full-string coordinates with a maximum
length of 71 characters. Returned content uses bounded canonical base64 syntax.
The worker rejects a result when the canonical JSON bytes, including the result
digest, exceed `max_transport_bytes`; raw file length alone is not treated as a
transport bound.

## Adapter ABI

`delegation-adapter-profile.schema.json` describes the Codex CLI first adapter,
the local/provider adapter, and the explicit ephemeral local worker profile.
All profiles use `aoa_delegation_class_v1`, set `provider_neutral_abi: true`,
set `uses_builtin_codex_subagents: false`, and are disabled by default.
The Codex CLI command is the exact `codex exec --json --disable multi_agent`
shape; a command that substitutes another executable, enables, or ambiguously
names the built-in lane is rejected by the pair assertion.
Each profile must also carry its own bounded, non-empty adapter identity before
the pair can be considered distinct.
The checked-in JSON descriptors under `profiles/` are the source-backed
coordinates for those factories; a descriptor is not a launch receipt.
