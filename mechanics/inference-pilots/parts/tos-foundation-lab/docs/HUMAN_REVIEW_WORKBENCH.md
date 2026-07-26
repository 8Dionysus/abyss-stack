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

## Human and machine fields

Human-owned fields include:

- transcription;
- layout or reading-order judgment;
- boundary judgment;
- legibility and uncertainty;
- decision and rationale;
- reviewer identity and final human-presence attestation.

Machine-owned fields include:

- packet and manifest identity;
- source-file and page-set digests;
- unit ordering and page routing;
- timestamps, autosave revision, and active-time observation;
- draft filename, digest, and freeze receipt;
- blind-lane enforcement that can be established mechanically.

A reviewer is never asked to attest that a digest was checked. The packet
verifier owns that statement.

Active time is a browser observation, not a human-authored fact or proof of
attention. It advances only while the review tab is visible and focused, stops
after ten minutes without interaction, and resumes on focus or interaction.
This keeps quiet source reading measurable without turning an abandoned tab
into unbounded human cost. Reports must retain that measurement method.

## First bounded slice

The first slice supports pass 1 for the two prepared Zarathustra packet
families:

- fifteen-page diplomatic human gold;
- thirty-unit German layout, boundary, and diplomatic source review.

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
- explicit final review and human attestation;
- a frozen draft plus SHA-256 receipt.

Pass 2, cross-pass blindness, adjudication, and accepted JSONL materialization
remain later stages. The first slice must not imply that a submitted pass-1
draft is gold or accepted German.

## Exposure and storage

- Bind only to `127.0.0.1`.
- Require a per-launch high-entropy token for API and page requests.
- Reject unexpected `Host` and cross-origin write requests.
- Serve only page assets resolved from the verified packet manifest.
- Write only under the declared mutable human-review session directory.
- Keep feedback screenshots content-addressed under
  `human-review-workbench.feedback-assets/`, owner-only, and referenced from the
  feedback JSONL by relative path, media type, size, and digest.
- Accept only bounded PNG, JPEG, or WebP feedback images: at most four,
  eight MiB each, and twelve MiB in total per feedback record.
- Hold an exclusive session lock while the Workbench is running so two local
  processes cannot overwrite the same mutable pass.
- Use atomic replacement and owner-only file modes.
- Keep all private source images and human drafts outside Git.

## Lifecycle

```text
ready -> in-progress -> submitted-and-frozen
```

`submitted-and-frozen` means only that one real human declared the pass
complete and the runtime fixed the resulting draft. It does not mean
double-checked, adjudicated, accepted, promoted, or correct.

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
