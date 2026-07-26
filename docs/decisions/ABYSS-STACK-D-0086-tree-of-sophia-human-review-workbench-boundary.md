# Tree of Sophia Human Review Workbench Boundary

- Decision ID: ABYSS-STACK-D-0086
- Status: accepted
- Date: 2026-07-25
- Owner surface: `mechanics/inference-pilots/parts/tos-foundation-lab/`

## Index Metadata

- Original date: 2026-07-25
- Surface classes: inference pilot, human review interface, source/runtime boundary, host storage
- Stack lanes: inference pilots, Tree of Sophia access, human review
- Mechanic parents: inference-pilots
- Guard families: independent reference, method-blind candidate review, language competence, loopback exposure, draft freeze
- Posture: accepted human-workbench boundary

## Context

The first Tree of Sophia foundation packets made the human-input boundary
mechanically explicit but operationally burdensome. A reviewer had to locate
private directories, correlate page triplets and unit identifiers, edit or
export structured files, preserve ordering and provenance, and remember which
artifacts were authoritative. Those tasks add friction without adding
philosophical or philological judgment, and the friction can itself reduce
review quality, completion rate, and the honest recording of uncertainty.

The route still cannot hide that this is real human work. Initial use also
exposed a second failure mode: applying independent full-page transcription to
ordinary OCR review makes the human reproduce machine work instead of judging
it. That cost is justified for a deliberately small anchoring-independent
reference, but not as the default comparison route.

A convenient interface must keep the kind of blindness explicit. It cannot
prefill an independent transcription or reveal candidates in an independent
reference lane. A candidate-review lane must show the candidate being judged
while hiding method identity and recognized references. Neither lane may
convert one pass into acceptance or let an application validator substitute
for source-visible judgment.

## Options considered

- Keep the generated static workbooks and require the reviewer to manage local
  files, exports, and merge steps manually.
- Use blank full-page transcription as the universal human-review primitive.
- Use criteria-only review without retaining a route for exact correction or
  independent calibration.
- Put the review application and mutable session state inside Tree of Sophia
  beside its source witnesses and authored meaning.
- Add a bounded loopback runtime adapter to the existing foundation laboratory,
  while Tree of Sophia retains protocol meaning and host storage remains under
  `abyss-machine`.

## Decision

The existing Tree of Sophia foundation laboratory owns a generic local Human
Review Workbench adapter. It consumes one already prepared private
`review-session.json`, re-verifies the immutable packet, binds only to
`127.0.0.1`, and uses a high-entropy per-launch token for its browser and API
route.

The Workbench automates mechanical responsibilities: admissible packet
resolution, source-page and candidate routing, unit ordering, required-field
visibility, language-scope propagation, candidate-prefilled correction,
atomic autosave, exact resume, timestamps, browser-observed active time,
feedback capture, output naming, digest calculation, and draft freeze. The
reviewer owns their language competence, source legibility, layout and reading
order, fragment boundaries, uncertainty, actual corrections, decisions,
rationale, identity, and explicit real-human attestation.

The Workbench supports typed review modes:

- an independent-reference lane hides model output, prior passes, recognized
  translations, and comparators and may request a small source-only
  transcription;
- a candidate-review lane shows the exact digest-frozen candidate while hiding
  the restricted method-identity map and recognized references;
- candidate correction begins from that candidate and records only the
  reviewer's edits, without converting them into source truth.

Writes remain inside the selected mutable session. Immutable packets and Tree
of Sophia source witnesses remain read-only. A reviewer who declares
`visual-only` competence for a language can contribute page, legibility, and
structure judgments, but cannot produce human orthographic, grammatical, or
semantic verification for that language.

The bounded interface supports the historical fifteen-page Human Gold packet
as a rare independent calibration pass, the thirty-unit language-competent
German source-review packet, and method-blind OCR A/B/C candidate-review
packets. Successful submission means only `pass-1-draft-frozen`. It does not
run an independent second pass, adjudicate disagreement, accept source text,
create gold, establish a general method ranking, authorize translation, or
promote a Tree of Sophia sign, concept, graph edge, or canon entry.

No persistent service is added for this slice. The stable
`scripts/aoa-tos-foundation-lab human-review-workbench` command starts the
session on demand; a server-hosted or multi-reviewer route requires a later
owner and threat-model decision.

## Rationale

The foundation laboratory already owns packet materialization, experiment
evidence, and manual-review runtime mechanics. Keeping the adapter there
avoids moving mutable runtime state into the philosophical source owner or
creating a rival laboratory. Keeping source meaning in Tree of Sophia and
storage/exposure policy in `abyss-machine` preserves the existing three-owner
boundary.

One focused unit, criteria before correction, prefilled repair, automatic
mechanics, and exact resume make the human route fast enough to repeat and
adapt without deciding content on the reviewer's behalf. Full transcription
remains available only where independence itself is the evidence being
created. A separate friction channel turns interface defects into research
evidence instead of allowing them to contaminate source decisions silently.
The explicit draft label and freeze receipt make convenience compatible with
later calibration and adjudication gates.

## Consequences

- Positive: the reviewer can begin from one operator command without browsing
  storage, copying hashes, editing JSON, or manually exporting each unit.
- Positive: immutable packet verification, blind-lane secrecy, autosave
  revisioning, reviewer identity, and draft digest are enforced consistently
  across supported protocols.
- Positive: uncertainty remains a first-class outcome, including an explicit
  uncertain German layout role where the prior interface and schema differed.
- Positive: human-facing friction becomes separately recordable and can be
  compared across later interface variants.
- Positive: ordinary OCR comparison no longer requires full-page retyping;
  criteria-only and corrected-text records remain distinguishable.
- Positive: every language claim is bounded by reviewer-declared competence,
  so visual German review cannot masquerade as German-language verification.
- Tradeoff: a criteria-only candidate review cannot yield exact character
  error metrics without a separate independent reference.
- Tradeoff: the first slice is single-session and local-loopback only; it does
  not yet coordinate concurrent reviewers or remote access.
- Tradeoff: browser-observed active time is a method measurement, not proof of
  attention or correctness.
- Follow-up: add pass 2 only after its independent identity and blindness
  contract can be shown in the interface; add adjudication only as a separate
  source-visible human role.

## Source surfaces

- `mechanics/inference-pilots/parts/tos-foundation-lab/AGENTS.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/README.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/docs/HUMAN_REVIEW_WORKBENCH.md`
- `mechanics/inference-pilots/parts/tos-foundation-lab/human_review_workbench.py`
- `mechanics/inference-pilots/parts/tos-foundation-lab/ocr_candidate_review.py`
- `mechanics/inference-pilots/parts/tos-foundation-lab/schemas/ocr-candidate-review-manifest.schema.json`
- `mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py`
- `mechanics/inference-pilots/parts/tos-foundation-lab/workbench/index.html`
- `mechanics/inference-pilots/parts/tos-foundation-lab/workbench/app.js`
- `mechanics/inference-pilots/parts/tos-foundation-lab/workbench/app.css`
- `mechanics/inference-pilots/parts/tos-foundation-lab/tests/test_human_review_workbench.py`
- `mechanics/inference-pilots/parts/tos-foundation-lab/tests/test_ocr_candidate_review.py`
- `scripts/aoa-tos-foundation-lab`

## Follow-up route

Return to Tree of Sophia for review-question meaning, source or translation
acceptance, semantic promotion, and any future server-side human-work contract.
Return to this laboratory for pass-2 and adjudication interface mechanics.
Return to `abyss-machine` before persistent service, remote exposure,
multi-user concurrency, or new host storage routes are admitted.
