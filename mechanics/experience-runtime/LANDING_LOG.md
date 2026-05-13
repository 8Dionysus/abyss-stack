# Experience Runtime Landing Log

## 2026-05-07 - Archive topology landing

- Created the `experience-runtime` mechanics package.
- Moved preserved experience docs, schemas, examples, and contract tests into
  package-local `legacy`.
- Added provenance and archive index surfaces for follow-up validation.

Validation status is recorded in the session report after path rewrites and
test execution.

## 2026-05-13 - Experience records distillation audit

- Reviewed the large legacy artifact family against active service ownership.
- Kept the preserved contract tests and `_v1` schema/example family in
  `legacy/artifacts/`.
- Added an active stop-line document under `parts/experience-records/docs/` so
  future passes do not promote archive-only material by inertia.
