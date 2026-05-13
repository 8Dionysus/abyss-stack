# Experience Runtime Distillation Log

## 2026-05-07

Moved the old flat experience runtime seed family into package-local legacy
without distilling new active runtime doctrine.

Still legacy:

- wave2-wave5 contract tests
- `_v1` schema filenames
- seed-derived storage, governance, adoption, release, and office docs
- late-found job/worker/storage-plan root docs that belonged to the same
  experience runtime seed family
- examples paired to those schemas

Future distillation should create quieter package docs only when a concrete
runtime service or storage path consumes the contract.

## 2026-05-13

Reviewed the legacy-heavy artifact family and kept it archive-only.

Reason: the schemas, examples, and tests are real preservation value, but no
current `abyss-stack` service, storage path, operator command, or runtime
validator consumes the family as an active contract. Several raw docs point to
stronger owner repositories for meaning and authority.

The active classification lives in
`parts/experience-records/docs/EXPERIENCE_RECORDS_DISTILLATION.md`.

## 2026-05-13 archive classification

Added `legacy/ARCHIVE_CLASSIFICATION.md` so the large preserved family is
grouped by runtime concern instead of remaining an undifferentiated legacy
mass.

Verdict remains archive-only until one concrete `abyss-stack` service, storage
path, operator command, or validator consumes a single family.
