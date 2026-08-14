# Close Nested Review Evidence Before Inference

- Decision ID: ABYSS-STACK-D-0121
- Status: accepted
- Date: 2026-08-13
- Owner surface: `mechanics/governed-execution/parts/external-codex-agent/external_codex_nested_evidence.py`

## Index Metadata

- Original date: 2026-08-13
- Surface classes: external actor runtime, independent review, evidence namespace, session latency
- Stack lanes: governed execution, validation, review
- Mechanic parents: governed-execution
- Guard families: digest binding, evidence closure, immutable identity, fail closed
- Posture: accepted pre-inference deterministic closure with exact serial fallback

## Context

An independent reviewer may receive terminal results from several earlier
external actors. Those producer reports and outputs correctly cite the stable
immutable IDs, source coordinates, validation observations, and output
manifest identities that existed in each producer session. The reviewer packet
necessarily assigns new stable IDs to the same actor-safe envelopes and may
use a newer source projection.

In a real combined stats/memo review, the model spent 401.52 seconds and about
1.99 million input tokens, then returned both semantically bounded writer
results for repair because their historical aliases and source coordinates did
not exist under the current reviewer namespace. A name-only scan was fast but
unsafe: 17 occurrences used names also present in the reviewer task while the
same names referred to different digests. Resolving historical `source:` refs
against the current reviewer workspace was also unsound: of 30 occurrences,
12 still named the same bytes, four named drifted bytes, and 14 named paths
absent from that workspace.

A read-only shadow comparison closed all 77 evidence occurrences through the
exact producer task, result, report, actor delta, final manifest, upstream
actor envelopes, validation receipts, and output digests. It detected all 17
same-name digest collisions and left zero unresolved refs. Repeated runs were
deterministic and completed below one second. This is a durable transport and
review-cost boundary, not a domain-proof or acceptance decision.

The first admitted real-session shadow showed that deterministic closure is a
correctness and restart-avoidance improvement, not yet a per-inference latency
improvement. It ran in 401.36 seconds versus the preserved 401.52-second
model-only run. The reviewer consumed 2,747,506 input tokens, of which
2,552,064 were cached, and 17,920 output tokens, versus 1,986,045 input,
1,832,192 cached, and 18,559 output tokens in the model-only run. The reviewer
nevertheless changed the substantive judgment from evidence-closure repair to
`completed`/`proceed`: both prior closure blockers were resolved and no
semantic blocker remained. The runtime then correctly failed the attempt
because the canonical post-inference report schema, unlike its specialized
session-local derivative, had not yet admitted the new runtime reference.
The first correction widened that canonical schema, but a preserved-packet
preflight then proved that doing so breaks the exact result-schema and
incarnation bindings of existing owner packets. The compatible correction
keeps the canonical owner ABI byte-stable and uses the already persisted,
identity-bound session-local derivative consistently for structured decoding,
post-inference admission, and later A2A export.

## Options considered

- Leave all transitive evidence reconstruction to the model. This preserves no
  new controller surface, but repeatedly spends model time on exact byte joins
  and can mistake namespace movement for a semantic defect.
- Accept an historical alias whenever the same name exists among reviewer
  inputs. This is fast but silently selects the wrong bytes when independent
  tasks reuse canonical names such as `agent-obligation`, `actor-mandate`, or
  `task-local-dag`.
- Rewrite historical refs to the current reviewer IDs or regenerate producer
  reports and outputs. This mutates content-addressed evidence, obscures what
  the producer actually returned, and converts a transport join into false
  source authorship.
- Resolve every historical `source:` ref against the current reviewer
  projection. This substitutes newer or unrelated owner bytes for the exact
  bytes the producer inspected and fails when the reviewer projection has a
  different owner surface.
- Generate a subordinate digest-bound namespace before inference, fail closed
  on any unresolved edge, and let the model perform only semantic judgment.

## Decision

For an `independent_review` packet containing one or more complete producer
graphs, the external Codex runtime deterministically closes nested evidence
before starting the model. The controller admits a producer only when the
current immutable packet contains an exact task and a runtime result whose
evidence binds that task, plus the result-bound report, actor delta, final
manifest, and every cited output.

A historical result that lacks any of those exact current task/report/delta/
output inputs is not a partial producer admission. It retains the previous
model-only review route. This compatibility fallback exposes no partial
namespace and therefore grants no inferred graph authority.

Each historical immutable ref is resolved through the producer task's original
input provenance and `source_artifact_digest` to exactly one current
actor-safe envelope. Names alone never select a target. Historical source refs
are validated against the producer final manifest and exact producer
projection, not the current reviewer workspace; the namespace carries the
bounded anchored excerpt and its digest. Runtime output refs require both a
final-manifest entry and an actor-delta edge to one admitted output. Validation
refs require one exact successful observation in the producer result's terminal
model-report attempt, whose number must equal `result.attempt_count`.
Reordered observations from resumed attempts do not affect selection; missing,
mismatched, or multiply successful observations inside that terminal attempt
remain fail-closed. The namespace records the selected producer attempt ID so
an independent reviewer can inspect the qualification without relying on array
order. Other valid final-manifest line,
top-level-member, and content-entry anchors bind the exact historical manifest
value rather than being misclassified as outputs.

The controller writes one content-addressed, read-only
`nested-evidence-namespace` derivative before inference. A reviewer may cite a
specific closed entry as
`runtime:nested-evidence-namespace#<entry-id>`. The namespace proves transport
closure only: the model must still judge the underlying claim, and owner
source remains stronger. Any missing, ambiguous, drifted, out-of-scope, secret-
shaped, schema-invalid, or false-anchor edge rejects preparation before model
execution. When no complete producer graph exists, ordinary single-session
review behavior remains unchanged.

`AOA_EXTERNAL_CODEX_NESTED_EVIDENCE=off` is the emergency rollback to the
previous model-only review route. The default remains exact deterministic
closure; rollback does not admit name-only mapping or rewrite prior artifacts.

## Rationale

The controller already owns immutable materialization, exact digests, actor
manifests, deltas, and runtime validation observations. Joining those exact
transport identities is therefore runtime work, while deciding whether the
evidence proves the domain claim remains reviewer work. This split removes
transport ambiguity and false repair loops without weakening the independent
semantic gate; the first real shadow does not support a claim that it reduces
the model's own inspection time or input-token volume.

Digest binding prevents silent same-name collisions. Producer-final source
binding prevents temporal substitution by a newer reviewer checkout. Keeping
the namespace subordinate and content-addressed preserves prior evidence
instead of laundering a compatibility rewrite into source truth. Fail-closed
preparation also avoids paying model latency for an evidence packet the
runtime can already prove incomplete.

## Consequences

- Positive: exact byte and anchor closure itself is a sub-second deterministic
  preflight and changed the measured real review from a false evidence repair
  to no remaining semantic blocker, avoiding a needless repair/review cycle.
- Positive: historical report/output bytes remain unchanged and independently
  inspectable.
- Positive: same-name collisions, source drift, missing historical paths,
  output-manifest gaps, and validation-receipt gaps become typed pre-inference
  failures rather than ambiguous reviewer prose.
- Positive: repeated fixed validations across writer resume attempts resolve
  only through the exact terminal report attempt, with the selected attempt
  identity carried in the namespace receipt.
- Positive: the namespace is reusable across combined reviewers and preserves
  an exact serial/model-only rollback without introducing alias trust.
- Tradeoff: reviewer packets that want deterministic transitive closure must
  carry the complete producer task/result/report/delta/output envelope;
  incomplete legacy packets remain on the more expensive model-only route.
- Tradeoff: bounded anchored excerpts keep exact historical bytes visible to
  semantic review, but the first real shadow increased input-token volume and
  did not reduce wall time because the reviewer still inspected owner sources
  and underlying immutable envelopes.
- Follow-up: rerun the admitted real reviewer after the session-local-schema fix;
  then compare end-to-end avoided retries as well as duration, input tokens,
  verdict equivalence, and unresolved-edge rates. Optimize namespace prompt
  weight separately rather than treating transport closure as a demonstrated
  inference-speed win.

## Source surfaces

- `mechanics/governed-execution/parts/external-codex-agent/external_codex_nested_evidence.py`
- `mechanics/governed-execution/parts/external-codex-agent/external_codex_agent.py`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-nested-evidence-namespace.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-report.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/schemas/external-codex-state.schema.json`
- `mechanics/governed-execution/parts/external-codex-agent/CONTRACT.md`
- `mechanics/governed-execution/parts/external-codex-agent/PROVENANCE.md`
- `mechanics/governed-execution/parts/external-codex-agent/VALIDATION.md`
- `mechanics/governed-execution/parts/external-codex-agent/tests/test_external_codex_agent.py`

## Follow-up route

The `abyss-stack` governed-execution owner should run one fresh read-only
combined reviewer with the namespace enabled and compare it to the preserved
model-only receipt. Any digest collision, source drift, schema evolution, or
verdict disagreement remains blocking and routes back to this controller
boundary; no result from this optimization claims domain-owner acceptance or
proof completion.
