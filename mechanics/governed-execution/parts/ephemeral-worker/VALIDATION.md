# Validation

Run:

```bash
python -m pytest -q mechanics/governed-execution/parts/ephemeral-worker/tests
python -m py_compile mechanics/governed-execution/parts/ephemeral-worker/ephemeral_worker.py
```

See [Shared repository checks](../../../../VALIDATION.md#shared-repository-checks) for this repository-wide check.

The focused tests cover disabled-by-default execution, explicit activation,
snapshot and content-digest checking, canonical absolute NUL-free paths,
no-follow traversal through execute-only parents, symlink rejection, canonical
base64 results, decoded-content and encoded-transport byte-boundary rejection,
content-addressed results, parent-retained responsibility, and common-ABI
Codex/local-provider adapter profiles. No live baseline, pilot, promotion,
eval, closeout, or acceptance is claimed by these checks.
