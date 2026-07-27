# Inference Pilots Landing Log

## 2026-05-07 - Initial package landing

Created the inference pilots package as a route home for local model pilots,
benchmarking, model profiles, and trial-backed promotion paths.

Validation followed the package and root validation routes.

## 2026-05-13 - Part-local docs topology

Moved LangGraph, llama.cpp, local-trial, benchmark, and promotion-loop docs into
their owning parts. Old pilot files remain under `legacy/trials/raw/`.

Validation followed the root source route.

## 2026-05-13 - Trial legacy specialization

Moved preserved W0-W6 trial docs and runner scripts under
`legacy/trials/`.

Validation followed the root source route.

## 2026-05-13 - Trial compatibility bridge cleanup

Renamed the active role-level compatibility adapter to
`parts/local-trials/trial_compatibility_bridge.py` so old stage labels remain
wire IDs rather than active module topology. Moved the LangGraph pilot
dependency manifest into `parts/langgraph-pilot/requirements.txt`.

Validation followed the root source route.

## 2026-07-25 - Tree of Sophia human review workbench

Added a loopback-only, tokenized human review workbench to the existing Tree of
Sophia foundation laboratory route. It verifies the immutable blind packet,
presents one source-visible unit at a time, autosaves and resumes the first
human pass, captures task-friction feedback and bounded private screenshots
separately, uses human-readable edition/page labels, and freezes only a
digest-bound pass-1 draft.

The first bounded slice supports the prepared 15-page Human Gold and 30-unit
German source-review protocols. It does not perform the independent second
pass, adjudicate, accept source text, or promote content into Tree of Sophia.

## 2026-07-25 - Criteria-first OCR review and correction

Separated ordinary method-blind OCR candidate review from the rare
content-blind independent calibration lane. The Workbench now shows a
digest-frozen candidate beside its source, collects fast criteria and error
tags, preloads correction text only on request, propagates declared
source-language competence, and prevents visual-only review from claiming
textual verification.

Added a private candidate-review packet materializer and verifier with
per-source randomized A/B/C display, a restricted unserved method map, exact
candidate/run provenance, a mutable-session initializer, and focused packet,
resume, correction, language-boundary, and freeze tests. Existing Human Gold
autosaves retain their internal protocol identity and are presented as
independent calibration drafts rather than completed gold.

## 2026-07-26 - Provenance-safe typography and review projection repair

Extended newly initialized OCR candidate sessions to protocol v2 with a
combined omission-plus-addition judgment and stand-off italic annotations
bound to Unicode positions plus exact quotes. Frozen and in-progress v1
sessions remain on their original schema and are never rewritten.

Autosave and freeze now synchronize the mutable `review-session.json` control
projection. Added an explicit idempotent repair command for valid completed
sessions whose control status predates the frozen human evidence.

Added a private, idempotent post-reveal analyzer that joins only a frozen human
draft to its restricted A/B/C map after re-verifying run and candidate
provenance. The report keeps quality, runtime, and observed human time
separate, and blocks correction-cost ranking when display positions are
imbalanced.
