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
4. this part's `README.md` and `docs/EXPERIMENT_LAW.md`;
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
- Runtime receipts may point to private local artifacts but committed examples
  and docs must stay public-safe and secret-free.

## Validation

```bash
python mechanics/inference-pilots/parts/tos-foundation-lab/tos_foundation_lab.py validate
python -m pytest mechanics/inference-pilots/parts/tos-foundation-lab/tests -q
python scripts/validate_stack.py
```
