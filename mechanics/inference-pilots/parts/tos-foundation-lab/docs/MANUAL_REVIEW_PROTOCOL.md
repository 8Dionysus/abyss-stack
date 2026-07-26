# Manual Source-Visible Review Protocol

## Rule

The reviewer sees the real page or anchored source passage and the actual
variant output. A validator report is never used as a substitute for this
comparison.

Candidate review is not independent transcription. The method name stays
hidden while its frozen output remains visible, and the reviewer evaluates it
by criteria or corrects only defective spans. Blank source-only transcription
is reserved for a small, explicitly independent calibration/reference lane.

## Before execution

1. Freeze the stratified sample plan before viewing system output.
2. Mark ordinary, random, and deliberately difficult samples.
3. Select a deliberately small independent calibration slice separately from
   the ordinary candidate-review workload.
4. Seal recognized translations for translation experiments.
5. Generate blind labels and keep the label map outside the review sheet.
6. Declare uncertainty and abstention as valid outcomes.

## Per sample

The reviewer records:

- source item, file, page/region/passage, and sample ID;
- whether the source itself is legible and correctly anchored;
- blind variant label;
- omissions, additions, substitutions, order errors, and anchor drift;
- task-specific errors such as semantic flattening, invented etymology,
  retrieval near-miss, or unsupported graph edge;
- severity, repair action, and correction minutes;
- `accept`, `accept_with_limits`, `reject`, `uncertain`, or `abstain`;
- a concrete rationale and optional counter-reading.
- their declared competence for the source language: full, partial, or
  visual-only.

For a `visual-only` language, the reviewer may record page identity,
legibility, cropping, block structure, and visible order. The record must leave
orthographic, grammatical, and semantic verification explicitly unassessed.
Historical spelling and authorial errors are source evidence, not defects to
normalize silently.

## Candidate review and correction

The ordinary OCR route shows one digest-frozen candidate beside the source
while concealing its method identity. The reviewer first records criteria and
quick error categories. If correction is useful, the Workbench preloads the
candidate and the reviewer changes only detected errors. The original
candidate digest, corrected text, decision, and observed human time remain
separate.

A criteria-only review can support comparative quality, usability, failure
categories, and human-cost analysis. It does not create an exact character
reference. Independent transcription is required only when exact reference
metrics or future regression comparisons justify that additional human cost.

## Gold-set double check

The first transcription is not gold merely because a human typed it. A later
source-visible pass compares it at full resolution and checks punctuation,
hyphenation, logical page boundaries, headers, and ambiguous glyphs.
Unresolved glyphs stay explicitly uncertain.

When only one human reviewer exists, a temporally separated second pass plus
AI comparison may produce a `solo-human calibration reference`; it must not be
reported as two-human gold or independent multi-reviewer agreement.

## Translation reveal sequence

1. freeze source transcription and analysis;
2. freeze human-only draft if a real human is available;
3. freeze AI-only draft and alternatives;
4. freeze the first AI+human revision;
5. reveal recognized translation witness;
6. record every material post-reveal change and whether it was accepted;
7. preserve rejected alternatives and the reason;
8. evaluate etymology only against cited external sources.

The recognized translation is a witness, not an answer key.

## Closeout

A comparison cannot close as promoted while any required hard sample lacks a
review or while the human-only lane is being represented by generated text.
The report must name missing human decisions and retain negative results.
