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
- Guard families: blind review, source-visible human review, loopback exposure, draft freeze
- Posture: accepted human-workbench boundary

## Context

The first Tree of Sophia foundation packets made the human-input boundary
mechanically explicit but operationally burdensome. A reviewer had to locate
private directories, correlate page triplets and unit identifiers, edit or
export structured files, preserve ordering and provenance, and remember which
artifacts were authoritative. Those tasks add friction without adding
philosophical or philological judgment, and the friction can itself reduce
review quality, completion rate, and the honest recording of uncertainty.

The route still cannot hide that this is real human work. A convenient
interface must not prefill a transcription, reveal model candidates or
recognized translations in a blind lane, convert one pass into acceptance, or
let an application validator substitute for source-visible judgment.

## Options considered

- Keep the generated static workbooks and require the reviewer to manage local
  files, exports, and merge steps manually.
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

The Workbench automates only mechanical responsibilities: admissible packet
resolution, source-page routing, unit ordering, required-field visibility,
atomic autosave, exact resume, timestamps, browser-observed active time,
feedback capture, output naming, digest calculation, and draft freeze. The
reviewer owns transcription, source legibility, layout and reading order,
fragment boundaries, uncertainty, decisions, rationale, identity, and the
explicit real-human attestation.

Blind payloads expose neither model output, prior-pass content, recognized
translation material, private filesystem paths, nor comparator data. Writes
remain inside the selected mutable session. The immutable packet and Tree of
Sophia source witnesses remain read-only.

The first bounded interface supports pass 1 for the prepared fifteen-page
Human Gold packet and thirty-unit German source-review packet. Successful
submission means only `pass-1-draft-frozen`. It does not run the independent
second pass, adjudicate disagreement, accept German source text, create gold,
authorize translation, or promote a Tree of Sophia sign, concept, graph edge,
or canon entry.

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

One focused unit, automatic mechanics, and exact resume make the human route
fast enough to repeat and adapt without deciding content on the reviewer's
behalf. A separate friction channel turns interface defects into research
evidence instead of allowing them to contaminate source decisions silently.
The explicit draft label and freeze receipt make convenience compatible with
the two-pass and adjudication gates.

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
- `mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py`
- `mechanics/inference-pilots/parts/tos-foundation-lab/workbench/index.html`
- `mechanics/inference-pilots/parts/tos-foundation-lab/workbench/app.js`
- `mechanics/inference-pilots/parts/tos-foundation-lab/workbench/app.css`
- `mechanics/inference-pilots/parts/tos-foundation-lab/tests/test_human_review_workbench.py`
- `scripts/aoa-tos-foundation-lab`

## Follow-up route

Return to Tree of Sophia for review-question meaning, source or translation
acceptance, semantic promotion, and any future server-side human-work contract.
Return to this laboratory for pass-2 and adjudication interface mechanics.
Return to `abyss-machine` before persistent service, remote exposure,
multi-user concurrency, or new host storage routes are admitted.
