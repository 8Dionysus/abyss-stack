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
  verification, navigation, autosave, timestamps, digests, and export
  mechanics; do not automate transcription, uncertainty, boundary, or
  acceptance judgments that the protocol assigns to the reviewer.
- Keep blind human lanes blind. Do not expose model candidates, prior passes,
  recognized translations, or comparator material through the UI or its
  public session payload.
- Human-review workbench writes must stay inside the selected mutable review
  session. The verified packet and Tree of Sophia source witnesses remain
  read-only.
- Feedback screenshots are private mutable-session evidence: accept only
  bounded image allowlists, store them content-addressed with owner-only modes,
  reference them relatively from feedback JSONL, and never serve them through
  the source-page route.
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
