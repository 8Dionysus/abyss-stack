# Provenance

One launch binds exact bytes from several owners without copying their
meaning into `abyss-stack`:

| Input | Meaning owner | Runtime use |
|---|---|---|
| `RunPlan` and `AgentIncarnationBinding` | `aoa-sdk` | validate plan, role/task participation, permission/continuation boundaries, and observe-only usage metering |
| role contract | `aoa-agents` | deliver the exact bounded role text |
| owner execution request, obligation, mandate, responsibility transfer, and domain procedure refs | `aoa-agents` and domain owners | admit the external incarnation only after responsibility has actually moved |
| task-local DAG | `aoa-skills` | prove the actor node is ready and remains a non-authoritative local projection of the goal |
| model realization | `aoa-models` | select only the caller-named model/effort/configuration |
| runtime/tool profile | `abyss-stack` | constrain Codex argv, tools, sandbox, network and effects |
| task and workspace sources | target/request owners | bind objective, transition, mutation/artifact paths, distinct source-evidence paths, and immutable inputs |
| canonical result schema and session-local identity-bound derivative | `abyss-stack` | constrain the model-authored report shape and mechanically bind exact task/incarnation IDs |
| runtime state/events/result and final workspace manifest | `abyss-stack` | record what process and thread actually ran, what bytes remained, and what it returned |

For read-only execution, `abyss-stack` owns the projection between two exact
paths: the target checkout remains outside Codex's writable roots, while an
attempt-local execution root and `TMPDIR` admit ephemeral validation writes.
The internal Codex sandbox is technically `workspace-write` only over that
runtime-owned root. The model realization and binding continue to describe the
semantic target-workspace posture as `read-only`; the runtime profile records
the implementation projection without converting it into task mutation
authority or `allowed_paths`.

The neutral binder consumes already selected coordinates and writes only the
runtime launch. Its response explicitly returns to `aoa-agents` to form the
separate owner execution request; it cannot choose the obligation, role,
model, domain procedure, or responsibility holder.

The live Codex bundled model catalog and executable digest are currentness
checks, not replacements for `aoa-models`. Runtime receipts are execution
evidence, not `aoa-evals` verdicts. The A2A export preserves the existing
downstream owner review rather than bypassing it.

The session-local output schema is derived only from the admitted canonical
schema plus the exact task and incarnation identities already present in
runtime state. Its path and digest are persisted and checked before inference;
the canonical schema is still used for source admission and final report
validation. Before every admitted continuation, the exact prior terminal
runtime result is copied into its attempt directory and retained as an
evidence ref rather than overwritten by the later terminal result. The narrow
failed-review route adds stricter failure/status/digest checks on top of this
general preservation rule.

Usage provenance is event-bounded. Numeric token counters are accumulated only
from Codex `turn.completed` records. When a controlled interruption precedes
that record, the runtime persists a typed observation gap keyed by attempt and
event sequence; resumed usage remains additive, while completeness remains
`partial` instead of treating an absent report as measured zero.

`allowed_paths` is mutation and produced-artifact authority;
`source_evidence_paths` is only the admissible workspace citation surface. The
runtime-owned final manifest cannot be an immutable pre-run input, so reports
address it through the reserved `runtime:workspace-final-manifest` identity.
The controller resolves that identity only to the manifest it writes during
the same attempt's finalization. This makes post-exit state citable without
turning an arbitrary runtime path into evidence.

`prepare_landing_study.py` verifies that the imported `aoa_sdk` package,
`compile_run_plan`, and every loaded `aoa_sdk` module or package path live
beneath the exact `--aoa-sdk-root/src/aoa_sdk` named by the caller. Hashing one
SDK checkout while importing any auxiliary module from another is rejected
before writer packets are materialized. After every writer plan and binding is
compiled, the preparer repeats that check and persists the complete loaded
module/search-path inventory in `study-preparation.json`; the receipt therefore
does not ask a later reviewer to infer SDK origin from an earlier guard alone.

The canonical reviewer preparer preserves every writer immutable input ID and
provenance ref, then adds the runtime-owned writer result, report, and a
distinct exact post-writer workspace manifest as new immutable evidence. For a
repo-mutation writer, the caller must explicitly supply the plan-bound
`aoa-agents` reviewer contract and the matching `aoa-models` read-only
realization; the preparer verifies that provider, runtime, model, and effort are
unchanged while permissions and tools narrow to read-only. It creates a
distinct task/incarnation/session, preserves the explicit source-evidence
scope, but starts no process. Historical lab-local
reviewer scripts remain trial provenance, not the source contract for future
candidates.

Machine-local deployment preserves this split by copying exact runtime-owner
files, the exact SDK package, the exact SDK incarnation/summon schemas, and the
pinned `aoa-agents`/`aoa-skills` owner schemas into separate release subtrees under one
content-addressed manifest. The release identity is a canonical digest over
every delivered path, size, and byte digest. The active receipt additionally
records all four Git HEADs and dirty postures, status digests, Python executable, and
the prior active release. At each invocation the wrapper seals those bytes and
materializes the complete manifest as a private read-only mount snapshot before
imports begin. This proves which local bytes a wrapper can execute;
it does not turn dirty source into a landed SDK/runtime release or substitute
for remote CI.
