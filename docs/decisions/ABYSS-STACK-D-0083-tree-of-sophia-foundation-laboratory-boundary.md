# Tree of Sophia Foundation Laboratory Boundary

- Decision ID: ABYSS-STACK-D-0083
- Status: accepted
- Date: 2026-07-22
- Owner surface: `mechanics/inference-pilots/parts/tos-foundation-lab/`

## Index Metadata

- Original date: 2026-07-22
- Surface classes: inference pilot, experiment contract, source/runtime boundary, host storage
- Stack lanes: inference pilots, machine fit, Tree of Sophia access
- Mechanic parents: inference-pilots, machine-fit
- Guard families: A/B/C freeze, manual review, resource preflight, source/runtime boundary
- Posture: accepted laboratory-owner rationale

## Context

Tree of Sophia now has a corpus evidence spine and local source items whose OCR,
structure, alignment, translation, annotation, retrieval, graph, and model
methods must be compared on real material. These trials require runtime and
machine evidence, potentially large caches and models, resource gates, failed
run preservation, and quality/cost/speed receipts. Those responsibilities do
not belong in the philosophical source owner.

At the same time, a generic benchmark runner is insufficient. A green runtime
packet cannot decide that source text, translation, etymology, sign, concept,
or graph edge is correct. The route must preserve a real human-only lane,
recognized-translation reveal order, source-visible manual review, uncertain
and abstain outcomes, and return-to-ToS provenance.

## Options considered

- Put OCR, translation, semantic, retrieval, and graph execution directly in
  Tree of Sophia beside the source witnesses.
- Create a standalone ToS laboratory repository or a second top-level
  `abyss-stack` lab hierarchy.
- Add one bounded Tree of Sophia foundation laboratory part to the existing
  inference-pilots mechanic, consuming machine-fit and `abyss-machine` policy
  while returning only reviewed derivative candidates to ToS.

## Decision

`mechanics/inference-pilots/parts/tos-foundation-lab/` owns the declarative and
runtime route for Tree of Sophia foundation experiments. Its frozen suite names
exactly A, B, and C variants for OCR, structure, alignment, translation,
semantic annotation, retrieval, graph projection, local LLM assistance, and
golden-kernel transfer.

The suite freezes the research question, source IDs, sample-plan reference,
rights posture, method candidates, resource gates, expected artifacts,
quality/speed/machine-cost/human-cost/traceability metrics, manual protocol,
stop conditions, and promotion conditions before results are inspected.
Missing methods remain `requires-setup` or `not-run`; missing humans remain
`awaiting-human-input` and are never simulated.

The stable operator route is `scripts/aoa-tos-foundation-lab`. It validates the
suite, captures a current host and `abyss-machine` storage preflight, and may
materialize an isolated run packet only after an allowed gate. Source payloads
remain immutable under the Tree of Sophia item route and are referenced by
stable IDs. Durable local run artifacts, caches, runtimes, and scratch output
route under the corresponding `/srv/abyss-machine/` owner paths and never into
Git.

Manual source-visible review remains the content authority. Runtime validation
may prove schema, reference, revision, artifact, hash, metric, and
reproducibility properties only. A reviewed derivative returns to Tree of
Sophia with its run ID, method revision, input anchors, rights basis, and human
review state; this mechanic cannot promote philosophical content or canon.

## Rationale

Inference-pilots already owns local trial execution, benchmark evidence, and
promotion candidates, while machine-fit and `abyss-machine` already own the
host capability and storage/resource boundaries. A part-local domain suite
therefore reuses the right runtime spine without creating a rival owner.

Freezing one public-safe suite makes method comparisons inspectable and stops
candidate availability from changing the question after results are seen. The
separate quality, speed, machine, and human-correction dimensions prevent a
fast but labor-intensive system from appearing cheap. Explicit manual review
and human-input states prevent schemas or models from masquerading as
philological judgment.

## Consequences

- Positive: ToS source evidence and stack runtime evidence remain in separate,
  resolvable owner surfaces.
- Positive: the first wave can reuse resident SQLite, Qdrant, Neo4j,
  OpenVINO, Gemma, and Qwen routes without downloading the entire shortlist.
- Positive: absent candidates, blocked resource gates, failed runs, negative
  transfer, uncertainty, and human correction cost stay visible.
- Positive: restricted source bytes are never required in committed examples
  or copied into lab source.
- Tradeoff: completing translation and semantic comparisons requires real
  human input and cannot be closed by automation alone.
- Tradeoff: OCR/document candidates remain blocked until one-at-a-time setup,
  licensing, storage, temperature, and retention gates pass.
- Follow-up: portable evaluation doctrine or cross-host model claims must move
  to `aoa-evals`; ToS content promotion must move through Tree of Sophia review.

## Source surfaces

- `mechanics/inference-pilots/parts/tos-foundation-lab/README.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/AGENTS.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/docs/EXPERIMENT_LAW.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/docs/MANUAL_REVIEW_PROTOCOL.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/docs/RESOURCE_GATE.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/examples/tos-foundation-suite.v1.json`
- `mechanics/inference-pilots/parts/tos-foundation-lab/schemas/experiment-suite.schema.json`
- `mechanics/inference-pilots/parts/tos-foundation-lab/schemas/run-receipt.schema.json`
- `mechanics/inference-pilots/parts/tos-foundation-lab/schemas/manual-review-receipt.schema.json`
- `mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py`
- `scripts/aoa-tos-foundation-lab`
- `mechanics/machine-fit/parts/inference-tuning/docs/MODEL_CARDS.md`

## Follow-up route

Revisit this decision if the suite becomes portable eval doctrine, if a domain
laboratory mechanic emerges that honestly supersedes inference-pilots, if host
storage ownership changes, or if Tree of Sophia adopts a reviewed server-side
execution boundary. Method and content promotions still require separate
evidence and owner decisions.
