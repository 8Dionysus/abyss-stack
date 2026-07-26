# ToS Human Review Workbench

## Purpose

The Workbench is the local human-facing edge of the Tree of Sophia foundation
laboratory. It turns an already verified blind review packet into one focused
review session without asking the reviewer to navigate storage, copy hashes,
edit JSON, or manage exports.

Human convenience is part of evidence quality. A packet can be mechanically
correct and still be a poor research instrument when the reviewer must carry
filesystem, provenance, or lifecycle mechanics in working memory.

## Interaction contract

The operator says that they are ready for human work. The runtime adapter then:

1. resolves one admissible prepared review session;
2. re-verifies its immutable packet and blank stop line;
3. opens a loopback-only browser session at the next unfinished unit;
4. autosaves human input into the mutable review-session directory;
5. resumes from the exact saved unit after interruption;
6. refuses submission while required human judgments are missing;
7. freezes a draft and digest receipt without claiming source acceptance.

The reviewer sees the source, the current task, their progress, and only the
fields that require human judgment. They do not handle artifact paths,
manifest hashes, packet ordering, output filenames, or JSONL merging.

## Ownership split

| Surface | Owner |
| --- | --- |
| source identity, review question, semantic meaning, acceptance law | Tree of Sophia |
| immutable page packet and experiment evidence | foundation laboratory |
| loopback UI, autosave, resume, draft freeze | this runtime adapter |
| host storage, browser process, resource and exposure policy | `abyss-machine` |
| final source, gold, translation, sign, or canon decision | real human review returned to Tree of Sophia |

The Workbench never edits the immutable packet and never promotes a draft into
Tree of Sophia. It only improves the route by which real human evidence is
created.

## Review modes

The interface distinguishes three different kinds of human work instead of
forcing every task through blank full-page transcription:

1. **Candidate review** is the normal comparison route. The source page and
   one frozen OCR candidate are visible together. Method identity is hidden,
   and the reviewer records criteria, error types, a decision, and an optional
   correction.
2. **Candidate correction** begins from the exact frozen candidate text. The
   reviewer edits only detected errors; the untouched candidate digest remains
   in the draft so correction effort can be measured honestly. Typography is
   recorded separately from text: the reviewer selects a corrected-text span,
   and the draft binds an italic annotation to both Unicode code-point offsets
   and the exact selected quote.
3. **Independent reference** keeps every candidate hidden and asks for a
   source-only transcription. It is deliberately rare and small because its
   purpose is to create an anchoring-independent calibration witness, not to
   become the default human workload.

Blindness is therefore typed. Independent-reference lanes are content-blind.
Candidate-review lanes are method-blind but candidate-visible. The packet
declares the mode, and the Workbench must never infer or switch it.

The existing fifteen-page packet retains its historical Human Gold packet
identity, but the Workbench presents its first pass as an independent
calibration draft. One pass is not gold. In a solo+AI workflow it must not be
reported as multi-human or independently double-checked evidence.

## Human and machine fields

Human-owned fields include:

- criteria-based candidate assessment;
- optional correction of a visible candidate;
- independent transcription only in the explicit reference lane;
- layout or reading-order judgment;
- boundary judgment;
- legibility and uncertainty;
- declared competence for each source language;
- decision and rationale;
- reviewer identity and final human-presence attestation.

Machine-owned fields include:

- packet and manifest identity;
- source-file and page-set digests;
- unit ordering and page routing;
- timestamps, autosave revision, and active-time observation;
- draft filename, digest, and freeze receipt;
- the mutable session-control projection derived from validated review state;
- blind-lane enforcement that can be established mechanically.

A reviewer is never asked to attest that a digest was checked. The packet
verifier owns that statement.

Language competence limits the claim. `full` permits textual fidelity review,
`partial` permits only confident textual judgments, and `visual-only` permits
page identity, legibility, and visible-structure review without orthographic,
grammatical, or semantic verification. The interface propagates the choice to
all units in that language and removes content fields that the reviewer cannot
honestly answer. Historical spelling is compared to the source, not corrected
to a modern grammar.

Active time is a browser observation, not a human-authored fact or proof of
attention. It advances only while the review tab is visible and focused, stops
after ten minutes without interaction, and resumes on focus or interaction.
This keeps quiet source reading measurable without turning an abandoned tab
into unbounded human cost. Reports must retain that measurement method.

## First bounded slice

The current slice supports three prepared Zarathustra review families:

- fifteen-page independent calibration pass using the historical Human Gold
  packet;
- thirty-unit German layout, boundary, and diplomatic source review.
- method-blind, candidate-visible OCR A/B/C review packets with criteria and
  candidate-prefilled correction.

It provides:

- one unit at a time;
- previous/current/next source navigation;
- zoom and fit controls;
- Russian interface copy;
- keyboard navigation;
- debounced atomic autosave;
- exact resume;
- a separate task-problem feedback channel;
- human-readable edition and page labels while retaining technical IDs only as
  secondary provenance;
- screenshot feedback by clipboard paste, file selection, or drag-and-drop;
- one combined completeness result for pages that contain both omissions and
  machine-added text;
- stand-off italic marking with removable chips and a source-text preview;
- explicit final review and human attestation;
- a frozen draft plus SHA-256 receipt.

Candidate review records language scope, candidate digest, criteria,
correction, typography selectors, error tags, decision, and human time without
exposing the method map. Typography syntax never enters `corrected_text`; if
that text changes, its old spans are cleared and must be selected again.
Pass 2, cross-pass blindness, adjudication, and accepted JSONL materialization
remain later stages. The first slice must not imply that a submitted draft is
gold, accepted German, or a general method ranking.

Candidate protocol v2 adds the combined completeness result and stand-off
typography. A session declares its protocol identity when it is initialized.
Already started or frozen v1 sessions continue under v1 and must reproduce the
same draft bytes; activation of v2 is not a migration of old human evidence.

## Exposure and storage

- Bind only to `127.0.0.1`.
- Require a per-launch high-entropy token for API and page requests.
- Reject unexpected `Host` and cross-origin write requests.
- Serve only page assets resolved from the verified packet manifest.
- Return candidate text only for a verified candidate-visible protocol; never
  return the restricted method-identity map.
- Write only under the declared mutable human-review session directory.
- Keep feedback screenshots content-addressed under
  `human-review-workbench.feedback-assets/`, owner-only, and referenced from the
  feedback JSONL by relative path, media type, size, and digest.
- Accept only bounded PNG, JPEG, or WebP feedback images: at most four,
  eight MiB each, and twelve MiB in total per feedback record.
- Hold an exclusive session lock while the Workbench is running so two local
  processes cannot overwrite the same mutable pass.
- Use atomic replacement and owner-only file modes.
- Treat `review-session.json` as a repairable control projection. Its progress
  and terminal status come from the validated autosave and, after freeze, the
  matching draft and receipt; the projection cannot overrule those artifacts.
- Keep all private source images and human drafts outside Git.

## Lifecycle

```text
ready -> in-progress -> submitted-and-frozen
```

`submitted-and-frozen` means only that one real human declared the pass
complete and the runtime fixed the resulting draft. It does not mean
double-checked, adjudicated, accepted, promoted, or correct.

Autosave and submission refresh the mutable control projection. The explicit
`sync-human-review-session-control` operator route can repair an older stale
projection after re-validating the complete artifact set; it never modifies
the autosave, draft, or receipt.

## Post-reveal analysis

Method identity remains sealed until the candidate draft is
`submitted-and-frozen`. The explicit `analyze-ocr-candidate-review` route then
re-verifies the draft, freeze receipt, immutable packet, restricted blind map,
run receipts, and source-candidate digests before writing a separate private
analysis and receipt under the mutable session's `post-reveal/` directory.
Nothing is joined back into the human draft.

The report keeps decisions, fidelity, completeness, structure, error types,
runtime evidence, and human active time as separate dimensions. It does not
order `accept-with-limits` against `corrected` or collapse them into a hidden
winner score. It also audits which revealed method occupied display positions
one, two, and three. When those positions are imbalanced, human-time and
correction-cost rankings are explicitly blocked because later candidates may
benefit from page familiarity and prior comparison.

## UX evaluation

Workbench quality is checked manually as its own research surface:

- time from operator command to first source-visible judgment;
- time and actions per unit;
- missing-field and correction frequency;
- resume accuracy;
- reviewer confidence and reported friction;
- whether interface pressure creates rushed or false certainty.

Speed is never allowed to erase disagreement, uncertainty, or difficult source
material.

Feedback is a first-class usability artifact, not part of the source judgment.
The reviewer may paste a screenshot directly into the open feedback dialog;
the note may be empty when the image carries the problem. The runtime keeps
these private captures beside the mutable session and never serves them back as
source pages or promotes them into Tree of Sophia.
