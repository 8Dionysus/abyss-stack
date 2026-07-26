# AGENTS.md

Applies to `mechanics/inference-pilots/parts/tos-foundation-lab/`.

## Role

This part owns reproducible, resource-gated local experiment orchestration for
Tree of Sophia source forensics, OCR, structure recovery, alignment,
translation, annotation, retrieval, graph projection, and bounded LLM trials.

It does not own source bytes, philosophical truth, accepted translations,
semantic promotion, rights clearance, model storage, or host policy.

## Read first

1. repository and `mechanics/` route cards;
2. `mechanics/inference-pilots/AGENTS.md` and package route docs;
3. `mechanics/machine-fit/AGENTS.md`;
4. this part's `README.md`, `docs/EXPERIMENT_LAW.md`, and, for human-facing
   work, `docs/HUMAN_REVIEW_WORKBENCH.md`;
5. `/etc/abyss-machine/AGENTS.md` and
   `/etc/abyss-machine/storage-policy.json` before any material run;
6. the current Tree of Sophia corpus contracts and rights records for every
   source item in the experiment.

## Non-negotiable boundaries

- Keep source payloads read-only and refer to them by stable ToS item/file IDs.
- Keep model/runtime/cache downloads under `/srv/abyss-machine`, never inside
  this repository or the ToS source tree.
- Run a current storage, memory, load, temperature, service-conflict, and
  license gate before every heavy execution.
- Do not install or download all candidates in a shortlist. Admit one candidate,
  run it, record retention, then consider the next.
- Preserve failed, stopped, uncertain, and abstained runs.
- Do not reveal recognized translations before the independent translation
  stage is frozen.
- Never synthesize a missing human-only lane.
- Validators may prove schema, paths, hashes, and reproducibility only. Manual
  source-visible review owns content acceptance.
- Treat human usability as part of evidence quality. Automate packet
  verification, navigation, autosave, timestamps, digests, export mechanics,
  and candidate-prefilled correction only when the declared task is candidate
  review. Never synthesize uncertainty, boundary, competence, correction, or
  acceptance judgments assigned to the reviewer.
- Keep independent-reference lanes content-blind: do not expose model
  candidates, prior passes, recognized translations, or comparator material.
  Keep candidate-review lanes method-blind instead: the frozen candidate text
  is visible, while the restricted method map and recognized references never
  enter the UI or its public session payload.
- Record the reviewer's declared competence for each source language. A
  visual-only reviewer may judge page identity, legibility, and visible
  structure, but their draft must not claim orthographic, grammatical, or
  semantic verification of that language.
- Do not make full-page retyping the default human route. Use source-visible
  criteria first, candidate-prefilled correction second, and an independent
  transcription only for a deliberately small calibration/reference lane.
- Preserve source typography as stand-off evidence. Do not insert Markdown or
  other presentation syntax into corrected source text; bind each typography
  span to both Unicode code-point offsets and its exact quoted text, and reject
  stale or overlapping selectors.
- Human-review workbench writes must stay inside the selected mutable review
  session. The verified packet and Tree of Sophia source witnesses remain
  read-only.
- Treat `review-session.json` as a mutable control projection, not review
  authority. Rebuild its progress and terminal status only from a validated
  autosave plus, after submission, the matching frozen draft and receipt.
- Feedback screenshots are private mutable-session evidence: accept only
  bounded image allowlists, store them content-addressed with owner-only modes,
  reference them relatively from feedback JSONL, and never serve them through
  the source-page route.
- OCR candidate-review packets are immutable private inputs. Serve candidate
  text only in their declared candidate-visible protocol, bind every text to
  its digest, and never serve or serialize the restricted method-identity map.
- Reveal method identity only after a complete draft is frozen. Post-reveal
  analysis must re-verify the draft, receipt, packet, restricted map, run
  receipts, and candidate digests; remain private; audit display-position
  balance; and block human-cost rankings when position is confounded.
- Preserve reviewer identity once a pass begins, require explicit real-human
  attestation at freeze, and label every workbench submission as a pass draft,
  never as gold, accepted source, translation, or canon.
- Mechanically green workbench tests do not replace a manual browser pass over
  the actual task flow, source visibility, resume behavior, and friction.
- Runtime receipts may point to private local artifacts but committed examples
  and docs must stay public-safe and secret-free.

## Validation

```bash
python mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py validate
python -m pytest mechanics/inference-pilots/parts/tos-foundation-lab/tests -q
python scripts/validate_stack.py
```
