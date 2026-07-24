# Manual Source-Visible Review Protocol

## Rule

The reviewer sees the real page or anchored source passage and the actual
variant output. A validator report is never used as a substitute for this
comparison.

## Before execution

1. Freeze the stratified sample plan before viewing system output.
2. Mark ordinary, random, and deliberately difficult samples.
3. Produce and independently recheck the manual gold slice.
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

## Gold-set double check

The first transcription is not gold merely because a human typed it. A second
pass compares it to the source at full resolution, checks punctuation,
hyphenation, line/page boundaries, headers, and ambiguous glyphs, and records
who performed each pass. Unresolved glyphs stay explicitly uncertain.

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
