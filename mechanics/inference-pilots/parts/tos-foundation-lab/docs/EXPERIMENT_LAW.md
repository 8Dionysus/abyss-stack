# Tree of Sophia Experiment Law

## Purpose

The laboratory compares methods, not brands. Every experiment freezes the
question, source IDs, sample plan, variants, resource gates, outputs, metrics,
manual review, stop-lines, and promotion conditions before inspecting variant
results.

## Lifecycle

```text
draft -> frozen -> preflighted -> running -> awaiting-manual-review
  -> accepted-with-limits | rejected | unresolved | stopped
```

`accepted-with-limits` means useful for the named task and sample only. It is
not a general model ranking and never promotes content into ToS canon.

## Variant law

- Each comparison carries exactly `A`, `B`, and `C`.
- Display order during review is randomized and recorded separately from the
  public method labels.
- A method that cannot run is retained as `not-run` with the exact missing
  dependency or resource gate; it is not silently replaced.
- Runtime and model revisions are exact when a run starts. A moving `latest`
  tag is insufficient evidence.
- A human-only variant remains unexecuted until a real human contributes it.
- Recognized translations stay sealed until independent drafts are frozen.
- OCR contestants share one pre-output, digest-frozen visual render; a
  contestant-specific rerender or preprocessing pass is a new experiment.
- Embedded ABBYY and same-edition EPUB OCR remain sealed reference witnesses
  until every independent OCR draft and digest is frozen.

## Evidence packet

Every executed run preserves:

- frozen experiment specification and its SHA-256;
- preflight and software/model inventory receipts;
- source IDs, sample IDs, and rights posture without copying restricted bytes;
- exact invocations or callable revisions;
- raw outputs, including failures;
- wall time, resource samples, and artifact sizes;
- computed metrics and the code/revision that computed them;
- randomized blind-label map in a restricted review file;
- manual review receipts and error ledger;
- final promotion/rejection/unresolved rationale;
- cleanup and retention decision.

An absent candidate may move from `requires-setup` to execution readiness only
through a schema-valid runtime manifest that proves the exact owner-contained
tree, commands, artifacts, licenses, acquisition receipts, and removal target.
Finding a similarly named command on `PATH` is not sufficient.

## Measurement law

Quality, speed, machine cost, and human correction cost remain separate. A fast
system with high correction time is not cheap. A high aggregate score cannot
erase catastrophic omissions, invented text, broken anchors, or semantic
flattening.

Automatic scores must be recomputed on at least one source-visible example by
hand. For OCR this includes character/word alignment inspection; for retrieval
it includes inspecting the actual ranked passages; for graph projections it
includes walking an edge back to its claim and evidence; for translation it
includes source-language reasoning and post-reveal change tracking.

## Owner handoff

`abyss-stack` may produce a derivative candidate and execution receipt. Tree of
Sophia owns any later source-near text, translation packet, sign annotation,
claim, review, or canon decision. A returned artifact must carry its originating
run ID, method revision, input anchors, rights basis, and human review state.
